using System.Security.Cryptography;
using System.Text.Json;

namespace GpwOffline;

public sealed class LocalService(Persistence store, bool allowProvisioning, TimeSpan sessionLifetime)
{
    private readonly object gate = new();
    private readonly Dictionary<string, Session> sessions = [];

    public Response Handle(Request request)
    {
        lock (gate)
        {
            try
            {
                if (request.Protocol != "GPW.local/1") throw new CoreFault("unsupported_protocol");
                object? result = request.Op switch
                {
                    "profile.create" => CreateProfile(request),
                    "session.open" => OpenSession(request),
                    "session.close" => CloseSession(request),
                    "profile.read" => ReadProfile(request),
                    "equipment.provision" => Provision(request),
                    "equipment.move" => Move(request),
                    "world.reserve" => throw new CoreFault("world_runtime_unimplemented"),
                    _ => throw new CoreFault("unsupported_operation")
                };
                return new Response(request.Id, true, "ok", result);
            }
            catch (CoreFault e) { return new Response(request.Id, false, e.Code, null); }
            catch (IOException) { return new Response(request.Id, false, "storage_io_error", null); }
            catch (UnauthorizedAccessException) { return new Response(request.Id, false, "storage_access_denied", null); }
            catch (OverflowException) { return new Response(request.Id, false, "revision_exhausted", null); }
        }
    }

    private object CreateProfile(Request r)
    {
        var uid = r.ProfileUid ?? throw new CoreFault("profile_uid_required");
        if (uid == Guid.Empty || string.IsNullOrWhiteSpace(r.Name) || r.Name.Length > 64 ||
            r.InventoryCapacity is not (>= 1 and <= 128) || r.WarehouseCapacity is not (>= 1 and <= 128))
            throw new CoreFault("invalid_profile");
        if (store.State.Profiles.ContainsKey(uid)) throw new CoreFault("profile_exists");
        var candidate = Json.Copy(store.State);
        var profile = new Profile { Uid = uid, Name = r.Name.Trim(), InventoryCapacity = r.InventoryCapacity.Value, WarehouseCapacity = r.WarehouseCapacity.Value };
        candidate.Profiles.Add(uid, profile);
        store.Commit(candidate);
        return new { profileUid = uid, revision = 0, gameInitialized = false };
    }

    private object OpenSession(Request r)
    {
        if (r.ProfileUid == null || !store.State.Profiles.ContainsKey(r.ProfileUid.Value)) throw new CoreFault("profile_not_found");
        foreach (var key in sessions.Where(s => s.Value.Expires <= DateTimeOffset.UtcNow).Select(s => s.Key).ToArray()) sessions.Remove(key);
        if (sessions.Count >= 1000) throw new CoreFault("session_limit");
        var token = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        var expires = DateTimeOffset.UtcNow.Add(sessionLifetime);
        sessions.Add(token, new Session(r.ProfileUid.Value, expires));
        return new { session = token, profileUid = r.ProfileUid, expires, scope = "GPW.local-only" };
    }

    private Profile Resolve(Request r)
    {
        if (r.Session == null || !sessions.TryGetValue(r.Session, out var session)) throw new CoreFault("invalid_session");
        if (session.Expires <= DateTimeOffset.UtcNow)
        {
            sessions.Remove(r.Session);
            throw new CoreFault("expired_session");
        }
        if (r.ProfileUid != session.ProfileUid) throw new CoreFault("profile_owner_mismatch");
        return store.State.Profiles[session.ProfileUid];
    }

    private object CloseSession(Request r)
    {
        Resolve(r);
        sessions.Remove(r.Session!);
        return new { closed = true };
    }

    private object ReadProfile(Request r)
    {
        var p = Resolve(r);
        return new { profileUid = p.Uid, p.Name, p.Revision, p.InventoryCapacity, p.WarehouseCapacity,
            equipment = p.Equipment.Values.OrderBy(e => e.Uid).ToArray(), storeGeneration = store.State.Generation,
            dataKind = "GPW-owned-equipment", gameInitialized = false };
    }

    private static void CheckRevision(Profile profile, long? revision)
    {
        if (revision == null) throw new CoreFault("expected_revision_required");
        if (revision != profile.Revision) throw new CoreFault("revision_conflict");
    }

    // Explicitly enabled developer provisioning. This is not a game reward or template initializer.
    private object Provision(Request r)
    {
        if (!allowProvisioning) throw new CoreFault("provisioning_disabled");
        var profile = Resolve(r);
        CheckRevision(profile, r.ExpectedRevision);
        if (r.Equipment == null || r.Equipment.Length is < 1 or > 256) throw new CoreFault("invalid_equipment_batch");
        var candidate = Json.Copy(store.State);
        var target = candidate.Profiles[profile.Uid];
        foreach (var item in r.Equipment)
        {
            if (item == null || !target.Equipment.TryAdd(item.Uid, item)) throw new CoreFault("duplicate_item_uid");
        }
        target.Revision = checked(target.Revision + 1);
        store.Commit(candidate); // shared structural, ownership and capacity validation
        return new { revision = target.Revision, provisioned = r.Equipment.Length, gameReward = false };
    }

    private object Move(Request r)
    {
        var profile = Resolve(r);
        var operation = r.OperationUid ?? throw new CoreFault("operation_uid_required");
        if (operation == Guid.Empty || r.ItemUids == null || r.ItemUids.Length is < 1 or > 256 ||
            r.ItemUids.Distinct().Count() != r.ItemUids.Length || r.ItemUids.Contains(Guid.Empty)) throw new CoreFault("invalid_move_batch");
        if (r.Destination is not ("inventory" or "warehouse")) throw new CoreFault("invalid_destination");
        var sorted = r.ItemUids.Order().ToArray();
        var fingerprint = Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(
            new { profile.Uid, r.ExpectedRevision, itemUids = sorted, r.Destination }, Json.Options)));
        if (profile.Receipts.TryGetValue(operation, out var prior))
        {
            if (prior.Fingerprint != fingerprint) throw new CoreFault("operation_uid_conflict");
            return new { revision = prior.Revision, itemUids = prior.ItemUids, destination = prior.Destination, replayed = true };
        }
        CheckRevision(profile, r.ExpectedRevision);
        if (profile.Receipts.Count >= 10000) throw new CoreFault("receipt_limit_requires_archival");
        foreach (var uid in sorted)
        {
            if (!profile.Equipment.TryGetValue(uid, out var item)) throw new CoreFault("item_not_owned");
            if (item.Equipped) throw new CoreFault("equipped_item");
            if (item.Location == r.Destination) throw new CoreFault("item_already_at_destination");
        }
        var capacity = r.Destination == "warehouse" ? profile.WarehouseCapacity : profile.InventoryCapacity;
        if (profile.Equipment.Values.Count(e => e.Location == r.Destination) + sorted.Length > capacity)
            throw new CoreFault("destination_full");
        var candidate = Json.Copy(store.State);
        var target = candidate.Profiles[profile.Uid];
        foreach (var uid in sorted) target.Equipment[uid] = target.Equipment[uid] with { Location = r.Destination };
        target.Revision = checked(target.Revision + 1);
        target.Receipts.Add(operation, new Receipt(fingerprint, target.Revision, sorted, r.Destination));
        store.Commit(candidate);
        return new { revision = target.Revision, itemUids = sorted, destination = r.Destination, replayed = false };
    }
}
