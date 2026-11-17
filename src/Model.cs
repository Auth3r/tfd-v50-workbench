using System.Text.Json;
using System.Text.Json.Serialization;

namespace GpwOffline;

public sealed class CoreFault(string code) : Exception(code)
{
    public string Code { get; } = code;
}

public static class Json
{
    public static readonly JsonSerializerOptions Options = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        MaxDepth = 32
    };
    public static T Copy<T>(T value) => JsonSerializer.Deserialize<T>(JsonSerializer.SerializeToUtf8Bytes(value, Options), Options)!;
}

// All DTOs below are GPW-owned v1 contracts. No V15 wire layout is claimed.
public sealed record Equipment(Guid Uid, int TemplateId, string Location, bool Equipped);
public sealed record Receipt(string Fingerprint, long Revision, Guid[] ItemUids, string Destination);
public sealed class Profile
{
    public Guid Uid { get; set; }
    public string Name { get; set; } = "";
    public long Revision { get; set; }
    public int InventoryCapacity { get; set; }
    public int WarehouseCapacity { get; set; }
    public Dictionary<Guid, Equipment> Equipment { get; set; } = [];
    public Dictionary<Guid, Receipt> Receipts { get; set; } = [];
}
public sealed class StoreState
{
    public string Format { get; set; } = "GPW.owned-save/1";
    public long Generation { get; set; }
    public Dictionary<Guid, Profile> Profiles { get; set; } = [];
}
public sealed record Envelope(string Format, string Payload, string Sha256);
public sealed record Session(Guid ProfileUid, DateTimeOffset Expires);

public sealed class Request
{
    public string Protocol { get; set; } = "GPW.local/1";
    public long Id { get; set; }
    public string Op { get; set; } = "";
    public string? Session { get; set; }
    public Guid? ProfileUid { get; set; }
    public string? Name { get; set; }
    public int? InventoryCapacity { get; set; }
    public int? WarehouseCapacity { get; set; }
    public long? ExpectedRevision { get; set; }
    public Guid? OperationUid { get; set; }
    public Guid[]? ItemUids { get; set; }
    public Equipment[]? Equipment { get; set; }
    public string? Destination { get; set; }
}
public sealed record Response(long Id, bool Ok, string Code, object? Data)
{
    public string Protocol => "GPW.local/1";
}
