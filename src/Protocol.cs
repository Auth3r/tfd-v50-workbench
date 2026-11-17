using System.Buffers.Binary;
using System.Net;
using System.Net.Sockets;
using System.Text.Json;

namespace GpwOffline;

public static class Protocol
{
    public const int MaxPayload = 65536; // GPW policy, not a recovered V15 limit

    public static async Task<byte[]?> Read(Stream stream, CancellationToken ct)
    {
        var header = new byte[8];
        if (await stream.ReadAsync(header.AsMemory(0, 1), ct) == 0) return null;
        await stream.ReadExactlyAsync(header.AsMemory(1), ct);
        if (!header.AsSpan(0, 4).SequenceEqual("GPW1"u8)) throw new CoreFault("foreign_protocol");
        var length = BinaryPrimitives.ReadInt32LittleEndian(header.AsSpan(4));
        if (length is < 2 or > MaxPayload) throw new CoreFault("frame_size_invalid");
        var body = new byte[length];
        await stream.ReadExactlyAsync(body, ct);
        return body;
    }

    public static byte[] Encode<T>(T value)
    {
        var body = JsonSerializer.SerializeToUtf8Bytes(value, Json.Options);
        if (body.Length > MaxPayload) throw new CoreFault("response_too_large");
        var frame = new byte[8 + body.Length];
        "GPW1"u8.CopyTo(frame);
        BinaryPrimitives.WriteInt32LittleEndian(frame.AsSpan(4), body.Length);
        body.CopyTo(frame.AsSpan(8));
        return frame;
    }

    public static Request Decode(byte[] body)
    {
        using var doc = JsonDocument.Parse(body, new JsonDocumentOptions { MaxDepth = 32 });
        CheckUniqueKeys(doc.RootElement);
        var r = doc.RootElement.Deserialize<Request>(Json.Options) ?? throw new CoreFault("invalid_request");
        if (r.Op == null || r.Id <= 0) throw new CoreFault("invalid_request");
        var allowed = new HashSet<string>(["protocol", "id", "op"]);
        allowed.UnionWith(r.Op switch
        {
            "profile.create" => ["profileUid", "name", "inventoryCapacity", "warehouseCapacity"],
            "session.open" => ["profileUid"],
            "session.close" or "profile.read" => ["profileUid", "session"],
            "equipment.provision" => ["profileUid", "session", "expectedRevision", "equipment"],
            "equipment.move" => ["profileUid", "session", "expectedRevision", "operationUid", "itemUids", "destination"],
            _ => Array.Empty<string>()
        });
        foreach (var field in doc.RootElement.EnumerateObject())
            if (!allowed.Contains(field.Name)) throw new CoreFault("unexpected_field");
        if (!doc.RootElement.TryGetProperty("protocol", out _)) throw new CoreFault("protocol_required");
        return r;
    }

    private static void CheckUniqueKeys(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var keys = new HashSet<string>();
            foreach (var property in element.EnumerateObject())
            {
                if (!keys.Add(property.Name)) throw new CoreFault("duplicate_json_key");
                CheckUniqueKeys(property.Value);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
            foreach (var child in element.EnumerateArray()) CheckUniqueKeys(child);
    }
}

public static class Server
{
    public static async Task Run(LocalService service, int port, int seconds)
    {
        using var lifetime = new CancellationTokenSource(TimeSpan.FromSeconds(seconds));
        var listener = new TcpListener(IPAddress.Loopback, port);
        listener.Start(16);
        var active = new List<Task>();
        using var slots = new SemaphoreSlim(16);
        Console.CancelKeyPress += Cancel;
        void Cancel(object? sender, ConsoleCancelEventArgs e) { e.Cancel = true; lifetime.Cancel(); }
        Console.WriteLine(JsonSerializer.Serialize(new { state = "ready", protocol = "GPW.local/1", port = ((IPEndPoint)listener.LocalEndpoint).Port,
            pid = Environment.ProcessId, gameConnected = false, worldRuntimeImplemented = false }, Json.Options));
        try
        {
            while (!lifetime.IsCancellationRequested)
            {
                await slots.WaitAsync(lifetime.Token);
                TcpClient client;
                try { client = await listener.AcceptTcpClientAsync(lifetime.Token); }
                catch { slots.Release(); throw; }
                active.RemoveAll(t => t.IsCompleted);
                active.Add(Handle(client));
            }
        }
        catch (OperationCanceledException) { }
        finally
        {
            listener.Stop();
            lifetime.Cancel();
            await Task.WhenAll(active);
            Console.CancelKeyPress -= Cancel;
        }
        Console.WriteLine("{\"state\":\"stopped\"}");

        async Task Handle(TcpClient client)
        {
            using (client)
            {
                try
                {
                    var stream = client.GetStream();
                    long lastId = 0;
                    while (!lifetime.IsCancellationRequested)
                    {
                        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
                        deadline.CancelAfter(TimeSpan.FromSeconds(5));
                        var payload = await Protocol.Read(stream, deadline.Token);
                        if (payload == null) break;
                        Response response;
                        try
                        {
                            var request = Protocol.Decode(payload);
                            if (request.Id <= lastId) throw new CoreFault("request_id_not_increasing");
                            lastId = request.Id;
                            response = service.Handle(request);
                        }
                        catch (CoreFault e) { response = new Response(0, false, e.Code, null); }
                        catch (JsonException) { response = new Response(0, false, "invalid_json_request", null); }
                        byte[] encoded;
                        try { encoded = Protocol.Encode(response); }
                        catch (CoreFault e) { encoded = Protocol.Encode(new Response(response.Id, false, e.Code, null)); }
                        await stream.WriteAsync(encoded, deadline.Token);
                    }
                }
                catch (Exception e) when (e is IOException or SocketException or OperationCanceledException or CoreFault) { }
                finally { slots.Release(); }
            }
        }
    }
}
