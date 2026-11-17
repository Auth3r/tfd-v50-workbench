using System.Security.Cryptography;
using System.Text.Json;

namespace GpwOffline;

public static class Paths
{
    public static string Root
    {
        get
        {
            for (var d = new DirectoryInfo(AppContext.BaseDirectory); d != null; d = d.Parent)
                if (File.Exists(Path.Combine(d.FullName, "GpwOffline.Core.csproj"))) return d.FullName;
            throw new CoreFault("project_root_not_found");
        }
    }
    public static string Within(string path, string parent)
    {
        var full = Path.GetFullPath(path);
        var root = Path.GetFullPath(parent).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        if (!full.StartsWith(root, StringComparison.OrdinalIgnoreCase)) throw new CoreFault("path_outside_owned_root");
        for (var current = full; current != null; current = Path.GetDirectoryName(current))
            if ((File.Exists(current) || Directory.Exists(current)) &&
                (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new CoreFault("reparse_point_refused");
        return full;
    }
    public static string Workspace(string name)
    {
        if (name.Length is < 1 or > 64 || name.Any(c => !char.IsAsciiLetterOrDigit(c) && c != '-'))
            throw new CoreFault("invalid_workspace_name");
        return Within(Path.Combine(Root, "data", name), Path.Combine(Root, "data"));
    }
}

public sealed class Persistence : IDisposable
{
    private readonly string directory;
    private readonly FileStream lease;
    private string Current => Safe("state.json");
    private string Previous => Safe("state.previous.json");
    public StoreState State { get; private set; } = new();
    private string Safe(string name) => Paths.Within(Path.Combine(directory, name), directory);

    public Persistence(string workspace, bool initialize = false, bool recovery = false)
    {
        directory = Paths.Workspace(workspace);
        if (initialize)
        {
            if (Directory.Exists(directory) && Directory.EnumerateFileSystemEntries(directory).Any())
                throw new CoreFault("workspace_not_empty");
            Directory.CreateDirectory(directory);
        }
        if (!Directory.Exists(directory)) throw new CoreFault("workspace_not_initialized");
        // A handle lock survives neither normal exit nor process death; never trust a saved PID.
        try { lease = new FileStream(Safe("workspace.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None); }
        catch (IOException) { throw new CoreFault("workspace_in_use"); }
        try
        {
            var marker = Safe("gpw-owned.txt");
            if (initialize)
            {
                File.WriteAllText(marker, "GPW Offline owned data v1\n");
                WriteState(Current, State);
            }
            if (!File.Exists(marker) || File.ReadAllText(marker) != "GPW Offline owned data v1\n")
                throw new CoreFault("foreign_workspace");
            if (!recovery) State = ReadState(Current);
        }
        catch { lease.Dispose(); throw; }
    }

    public static void Validate(StoreState state)
    {
        if (state.Format != "GPW.owned-save/1" || state.Generation < 0 || state.Profiles == null || state.Profiles.Count > 1000)
            throw new CoreFault("unsupported_or_invalid_save");
        var globalItems = new HashSet<Guid>();
        foreach (var (id, p) in state.Profiles)
        {
            if (p == null || id == Guid.Empty || id != p.Uid || string.IsNullOrWhiteSpace(p.Name) || p.Name.Length > 64 ||
                p.Revision < 0 || p.InventoryCapacity is < 1 or > 128 || p.WarehouseCapacity is < 1 or > 128 ||
                p.Equipment == null || p.Receipts == null || p.Receipts.Count > 10000)
                throw new CoreFault("invalid_profile");
            foreach (var (itemId, item) in p.Equipment)
                if (item == null || itemId == Guid.Empty || itemId != item.Uid || !globalItems.Add(itemId) ||
                    item.TemplateId <= 0 || item.Location is not ("inventory" or "warehouse") || (item.Equipped && item.Location != "inventory"))
                    throw new CoreFault("invalid_equipment");
            if (p.Equipment.Values.Count(e => e.Location == "inventory") > p.InventoryCapacity ||
                p.Equipment.Values.Count(e => e.Location == "warehouse") > p.WarehouseCapacity)
                throw new CoreFault("capacity_exceeded");
            foreach (var (operation, receipt) in p.Receipts)
                if (operation == Guid.Empty || receipt == null || receipt.Revision < 1 || receipt.Revision > p.Revision ||
                    receipt.ItemUids == null || receipt.ItemUids.Length is < 1 or > 256 ||
                    receipt.ItemUids.Distinct().Count() != receipt.ItemUids.Length || receipt.ItemUids.Any(i => !p.Equipment.ContainsKey(i)) ||
                    receipt.Destination is not ("inventory" or "warehouse") || receipt.Fingerprint?.Length != 64)
                    throw new CoreFault("invalid_receipt");
        }
    }

    public static StoreState ReadState(string path)
    {
        try
        {
            if (new FileInfo(path).Length > 32 * 1024 * 1024) throw new CoreFault("save_too_large");
            var envelope = JsonSerializer.Deserialize<Envelope>(File.ReadAllBytes(path), Json.Options) ?? throw new CoreFault("corrupt_save");
            if (envelope.Format != "GPW.snapshot/1") throw new CoreFault("unsupported_save_version");
            var payload = Convert.FromBase64String(envelope.Payload);
            if (!CryptographicOperations.FixedTimeEquals(SHA256.HashData(payload), Convert.FromHexString(envelope.Sha256)))
                throw new CoreFault("save_checksum_mismatch");
            var state = JsonSerializer.Deserialize<StoreState>(payload, Json.Options) ?? throw new CoreFault("corrupt_save");
            Validate(state);
            return state;
        }
        catch (Exception e) when (e is JsonException or FormatException or ArgumentException or NullReferenceException or IOException)
        { throw new CoreFault("corrupt_or_unreadable_save"); }
    }

    private static void WriteState(string path, StoreState state)
    {
        Validate(state);
        var payload = JsonSerializer.SerializeToUtf8Bytes(state, Json.Options);
        var bytes = JsonSerializer.SerializeToUtf8Bytes(new Envelope("GPW.snapshot/1", Convert.ToBase64String(payload), Convert.ToHexString(SHA256.HashData(payload))), Json.Options);
        if (bytes.Length > 32 * 1024 * 1024) throw new CoreFault("save_too_large");
        using var file = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        file.Write(bytes);
        file.Flush(flushToDisk: true);
    }

    public void Commit(StoreState candidate)
    {
        candidate.Generation = checked(State.Generation + 1);
        var temp = Safe($"pending-{Guid.NewGuid():N}.json");
        try
        {
            WriteState(temp, candidate);
            File.Replace(temp, Current, Previous); // atomic replacement on the same volume
            State = candidate; // publish only after durable file commit
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }

    public object RecoverPrevious(long expectedGeneration)
    {
        var previous = ReadState(Previous);
        if (previous.Generation != expectedGeneration) throw new CoreFault("recovery_generation_mismatch");
        var temp = Safe($"recovery-{Guid.NewGuid():N}.json");
        var retained = Safe($"pre-recovery-{Guid.NewGuid():N}.json");
        WriteState(temp, previous);
        try
        {
            if (File.Exists(Current)) File.Replace(temp, Current, retained);
            else File.Move(temp, Current);
            State = previous;
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
        return new { restoredGeneration = previous.Generation, retainedOriginal = Path.GetFileName(retained), sessionsInvalidated = true };
    }
    public object DescribePrevious()
    {
        var previous = ReadState(Previous);
        return new { generation = previous.Generation, profiles = previous.Profiles.Count,
            equipment = previous.Profiles.Values.Sum(p => p.Equipment.Count), recoveryRollsBackToThisGeneration = true };
    }
    public void Dispose() => lease.Dispose();
}
