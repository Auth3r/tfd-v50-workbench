using System.Buffers.Binary;
using System.Diagnostics;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace GpwOffline;

// Tests drive real child processes and TCP. There are no mock stores or fake game clients.
public static class SelfTest
{
    private static readonly List<object> Steps = [];
    private static int failures;
    private static void Assert(bool condition, string detail)
    { if (!condition) throw new Exception(detail); }
    private static async Task Check(string name, Func<Task> test)
    {
        try { await test(); Steps.Add(new { step = name, passed = true }); }
        catch (Exception e) { failures++; Steps.Add(new { step = name, passed = false, detail = e.Message }); }
    }

    private sealed class Child : IDisposable
    {
        public Process Process { get; }
        public int Port { get; private set; }
        public Child(params string[] args)
        {
            var start = new ProcessStartInfo("dotnet") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true, WorkingDirectory = Paths.Root };
            start.ArgumentList.Add(Assembly.GetExecutingAssembly().Location);
            foreach (var arg in args) start.ArgumentList.Add(arg);
            Process = Process.Start(start) ?? throw new Exception("child_not_started");
        }
        public async Task Ready()
        {
            var line = await Process.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(10));
            using var doc = JsonDocument.Parse(line ?? "{}");
            Assert(doc.RootElement.TryGetProperty("state", out var state) && state.GetString() == "ready", "child_not_ready");
            Port = doc.RootElement.GetProperty("port").GetInt32();
        }
        public async Task<int> Exit()
        {
            await Process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(10));
            return Process.ExitCode;
        }
        public void Dispose()
        {
            if (!Process.HasExited) { Process.Kill(); Process.WaitForExit(5000); }
            Process.Dispose();
        }
    }

    // Independent test framing: no Protocol.Encode/Read/Decode shared with the server.
    private sealed class Client : IDisposable
    {
        private readonly TcpClient tcp = new();
        private long next;
        public NetworkStream Stream => tcp.GetStream();
        public Client(int port) => tcp.Connect("127.0.0.1", port);
        public byte[] Frame(object request)
        {
            var node = JsonSerializer.SerializeToNode(request, Json.Options)!.AsObject();
            node["protocol"] ??= "GPW.local/1";
            node["id"] = ++next;
            var bytes = Encoding.UTF8.GetBytes(node.ToJsonString());
            var frame = new byte[bytes.Length + 8];
            frame[0] = 0x47; frame[1] = 0x50; frame[2] = 0x57; frame[3] = 0x31;
            BinaryPrimitives.WriteInt32LittleEndian(frame.AsSpan(4), bytes.Length);
            bytes.CopyTo(frame.AsSpan(8));
            return frame;
        }
        public async Task<JsonElement> Receive()
        {
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            var header = new byte[8];
            await Stream.ReadExactlyAsync(header, deadline.Token);
            Assert(header.AsSpan(0, 4).SequenceEqual(new byte[] { 0x47, 0x50, 0x57, 0x31 }), "response_magic");
            var length = BinaryPrimitives.ReadInt32LittleEndian(header.AsSpan(4));
            Assert(length is > 0 and <= 65536, "response_length");
            var body = new byte[length];
            await Stream.ReadExactlyAsync(body, deadline.Token);
            return JsonDocument.Parse(body).RootElement.Clone();
        }
        public async Task<JsonElement> Send(object request, string expected = "ok")
        {
            var frame = Frame(request);
            await Stream.WriteAsync(frame);
            var response = await Receive();
            Assert(response.GetProperty("id").GetInt64() == next || response.GetProperty("id").GetInt64() == 0, "response_correlation");
            Assert(response.GetProperty("code").GetString() == expected, $"expected_{expected}_got_{response.GetProperty("code").GetString()}");
            Assert(response.GetProperty("ok").GetBoolean() == (expected == "ok"), "response_success_flag");
            return response.TryGetProperty("data", out var data) ? data.Clone() : default;
        }
        public void Dispose() => tcp.Dispose();
    }

    public static async Task<int> Run(string report)
    {
        report = Paths.Within(report, Paths.Root);
        Steps.Clear(); failures = 0;
        var workspace = "test-" + Guid.NewGuid().ToString("N");
        var directory = Paths.Workspace(workspace);
        Child? host = null;
        var account = Guid.NewGuid(); var other = Guid.NewGuid();
        var a = Guid.NewGuid(); var b = Guid.NewGuid(); var equipped = Guid.NewGuid(); var d = Guid.NewGuid();
        var operation = Guid.NewGuid();
        try
        {
            using (var init = new Child("init", "--workspace", workspace)) Assert(await init.Exit() == 0, "init_failed");
            host = new Child("serve", "--workspace", workspace, "--seconds", "120", "--allow-provisioning");
            await host.Ready();
            using var client = new Client(host.Port);
            await Check("create_local_profiles", async () =>
            {
                await client.Send(new { op = "profile.create", profileUid = account, name = "GPW Test", inventoryCapacity = 4, warehouseCapacity = 2 });
                await client.Send(new { op = "profile.create", profileUid = other, name = "Other", inventoryCapacity = 4, warehouseCapacity = 2 });
                await client.Send(new { op = "profile.create", profileUid = account, name = "Duplicate", inventoryCapacity = 4, warehouseCapacity = 2 }, "profile_exists");
            });
            var opened = await client.Send(new { op = "session.open", profileUid = account });
            var token = opened.GetProperty("session").GetString()!;
            object Read(string? t = null) => new { op = "profile.read", profileUid = account, session = t ?? token };
            object Move(long revision, Guid[] ids, string destination, Guid? uid = null) => new
            { op = "equipment.move", profileUid = account, session = token, expectedRevision = revision, operationUid = uid ?? Guid.NewGuid(), itemUids = ids, destination };
            var originalMove = Move(1, [a, b], "warehouse", operation);
            await Check("provision_owned_equipment", async () =>
            {
                await client.Send(new { op = "equipment.provision", profileUid = account, session = token, expectedRevision = 0,
                    equipment = new[] { new Equipment(a, 101, "inventory", false), new Equipment(b, 102, "inventory", false), new Equipment(equipped, 103, "inventory", true), new Equipment(d, 104, "inventory", false) } });
                var data = await client.Send(Read());
                Assert(data.GetProperty("revision").GetInt64() == 1 && data.GetProperty("equipment").GetArrayLength() == 4, "provision_readback");
            });
            await Check("session_ownership_enforced", async () =>
            {
                await client.Send(new { op = "profile.read", profileUid = other, session = token }, "profile_owner_mismatch");
                await client.Send(Read("invalid-local-token"), "invalid_session");
            });
            await Check("atomic_warehouse_deposit", async () =>
            {
                var result = await client.Send(originalMove);
                Assert(result.GetProperty("revision").GetInt64() == 2, "deposit_revision");
                var data = await client.Send(Read());
                Assert(data.GetProperty("equipment").EnumerateArray().Count(e => e.GetProperty("location").GetString() == "warehouse") == 2, "warehouse_quantity");
                Assert(data.GetProperty("equipment").GetArrayLength() == 4, "item_conservation");
            });
            await Check("persistent_idempotency_and_conflict", async () =>
            {
                var replay = await client.Send(originalMove);
                Assert(replay.GetProperty("replayed").GetBoolean() && replay.GetProperty("revision").GetInt64() == 2, "duplicate_move_not_replayed");
                await client.Send(Move(1, [a], "warehouse", operation), "operation_uid_conflict");
            });
            await Check("reject_stale_revision_without_writes", async () =>
            {
                var before = SHA256.HashData(File.ReadAllBytes(Path.Combine(directory, "state.json")));
                await client.Send(Move(1, [a], "inventory"), "revision_conflict");
                Assert(before.SequenceEqual(SHA256.HashData(File.ReadAllBytes(Path.Combine(directory, "state.json")))), "stale_request_changed_disk");
            });
            await Check("batch_failures_are_atomic", async () =>
            {
                var before = File.ReadAllBytes(Path.Combine(directory, "state.json"));
                await client.Send(Move(2, [d], "warehouse"), "destination_full");
                await client.Send(Move(2, [equipped], "warehouse"), "equipped_item");
                await client.Send(Move(2, [a, Guid.NewGuid()], "inventory"), "item_not_owned");
                await client.Send(Move(2, [a, a], "inventory"), "invalid_move_batch");
                Assert(before.SequenceEqual(File.ReadAllBytes(Path.Combine(directory, "state.json"))), "rejected_batch_changed_disk");
            });
            await Check("concurrent_withdrawal_has_one_winner", async () =>
            {
                using var second = new Client(host.Port);
                var fa = client.Frame(Move(2, [a], "inventory"));
                var fb = second.Frame(Move(2, [b], "inventory"));
                await Task.WhenAll(client.Stream.WriteAsync(fa).AsTask(), second.Stream.WriteAsync(fb).AsTask());
                var results = await Task.WhenAll(client.Receive(), second.Receive());
                Assert(results.Count(r => r.GetProperty("code").GetString() == "ok") == 1 && results.Count(r => r.GetProperty("code").GetString() == "revision_conflict") == 1, "concurrent_lost_update");
                var data = await client.Send(Read());
                Assert(data.GetProperty("revision").GetInt64() == 3 && data.GetProperty("equipment").EnumerateArray().Count(e => e.GetProperty("location").GetString() == "warehouse") == 1, "concurrent_result");
            });
            await Check("fragmented_and_coalesced_transport", async () =>
            {
                var first = client.Frame(Read()); var second = client.Frame(Read());
                await client.Stream.WriteAsync(first.AsMemory(0, 3));
                await client.Stream.WriteAsync(first.AsMemory(3));
                await client.Stream.WriteAsync(second);
                var one = await client.Receive(); var two = await client.Receive();
                Assert(one.GetProperty("ok").GetBoolean() && two.GetProperty("ok").GetBoolean() && two.GetProperty("id").GetInt64() == one.GetProperty("id").GetInt64() + 1, "stream_reassembly");
            });
            await Check("unsupported_world_and_protocol_refused", async () =>
            {
                await client.Send(new { op = "world.reserve" }, "world_runtime_unimplemented");
                await client.Send(new { op = "session.open", profileUid = account, protocol = "V15" }, "unsupported_protocol");
                using (var broken = new Client(host.Port)) await broken.Stream.WriteAsync(new byte[] { 0x47, 0x50, 0x57 });
                await client.Send(Read());
            });
            await Check("malformed_and_foreign_frames_are_rejected", async () =>
            {
                await client.Send(new { op = "session.open", profileUid = account, unused = true }, "invalid_json_request");
                using (var invalid = new Client(host.Port))
                {
                    var body = Encoding.UTF8.GetBytes("{\"protocol\":\"GPW.local/1\",\"id\":1,\"op\":\"world.reserve\",\"op\":\"session.open\"}");
                    var header = new byte[] { 0x47, 0x50, 0x57, 0x31, 0, 0, 0, 0 };
                    BinaryPrimitives.WriteInt32LittleEndian(header.AsSpan(4), body.Length);
                    await invalid.Stream.WriteAsync(header); await invalid.Stream.WriteAsync(body);
                    var result = await invalid.Receive();
                    Assert(result.GetProperty("code").GetString() == "duplicate_json_key", "ambiguous_json_accepted");
                }
                foreach (var header in new[] { new byte[] { 0x47, 0x50, 0x57, 0x31, 1, 0, 1, 0 }, new byte[] { 0, 0, 0, 0, 2, 0, 0, 0 } })
                {
                    using var invalid = new Client(host.Port);
                    await invalid.Stream.WriteAsync(header);
                    using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(3));
                    Assert(await invalid.Stream.ReadAsync(new byte[1], timeout.Token) == 0, "invalid_header_not_closed");
                }
                await client.Send(Read());
            });
            await Check("failed_disk_commit_does_not_publish_state", async () =>
            {
                var data = await client.Send(Read());
                var warehouseItem = data.GetProperty("equipment").EnumerateArray().Single(e => e.GetProperty("location").GetString() == "warehouse").GetProperty("uid").GetGuid();
                var before = File.ReadAllBytes(Path.Combine(directory, "state.json"));
                using (var locked = new FileStream(Path.Combine(directory, "state.json"), FileMode.Open, FileAccess.Read, FileShare.None))
                    await client.Send(Move(3, [warehouseItem], "inventory"), "storage_io_error");
                Assert((await client.Send(Read())).GetRawText() == data.GetRawText(), "failed_commit_changed_memory");
                Assert(before.SequenceEqual(File.ReadAllBytes(Path.Combine(directory, "state.json"))), "failed_commit_changed_disk");
            });
            await Check("exclusive_workspace_lease", async () =>
            {
                using var duplicate = new Child("serve", "--workspace", workspace, "--seconds", "1");
                Assert(await duplicate.Exit() == 2, "second_writer_allowed");
            });
            var beforeRestart = (await client.Send(Read())).GetRawText();
            host.Dispose(); host = null;
            host = new Child("serve", "--workspace", workspace, "--seconds", "120");
            await host.Ready();
            using var restarted = new Client(host.Port);
            await Check("crash_restart_preserves_commits_and_receipts", async () =>
            {
                await restarted.Send(Read(), "invalid_session");
                var session = await restarted.Send(new { op = "session.open", profileUid = account });
                token = session.GetProperty("session").GetString()!;
                Assert((await restarted.Send(Read())).GetRawText() == beforeRestart, "restart_data_changed");
                var replay = await restarted.Send(Move(1, [a, b], "warehouse", operation));
                Assert(replay.GetProperty("replayed").GetBoolean(), "receipt_not_persisted");
                await restarted.Send(new { op = "equipment.provision", profileUid = account, session = token, expectedRevision = 3, equipment = new[] { new Equipment(Guid.NewGuid(), 105, "inventory", false) } }, "provisioning_disabled");
            });
            await Check("logout_revokes_local_session", async () =>
            {
                await restarted.Send(new { op = "session.close", profileUid = account, session = token });
                await restarted.Send(Read(), "invalid_session");
            });
            host.Dispose(); host = null;
            long previousGeneration;
            using (var info = new Child("recovery-info", "--workspace", workspace))
            {
                Assert(await info.Exit() == 0, "recovery_info_failed");
                previousGeneration = JsonDocument.Parse(await info.Process.StandardOutput.ReadToEndAsync()).RootElement.GetProperty("generation").GetInt64();
            }
            await Check("checksum_detects_changed_snapshot", async () =>
            {
                var path = Path.Combine(directory, "state.json");
                var envelope = JsonNode.Parse(File.ReadAllText(path))!.AsObject();
                envelope["sha256"] = new string('0', 64);
                File.WriteAllText(path, envelope.ToJsonString());
                using var corrupt = new Child("serve", "--workspace", workspace, "--seconds", "1");
                Assert(await corrupt.Exit() == 2, "bad_checksum_accepted");
                Assert((await corrupt.Process.StandardOutput.ReadToEndAsync()).Contains("save_checksum_mismatch", StringComparison.Ordinal), "checksum_not_checked");
            });
            File.WriteAllText(Path.Combine(directory, "state.json"), "deliberately corrupt owned test data");
            await Check("corruption_refused_explicit_recovery", async () =>
            {
                using (var corrupt = new Child("serve", "--workspace", workspace, "--seconds", "1")) Assert(await corrupt.Exit() == 2, "corruption_accepted");
                using (var wrong = new Child("recover-previous", "--workspace", workspace, "--generation", (previousGeneration + 1).ToString())) Assert(await wrong.Exit() == 2, "wrong_recovery_point_accepted");
                using (var recover = new Child("recover-previous", "--workspace", workspace, "--generation", previousGeneration.ToString())) Assert(await recover.Exit() == 0, "recovery_failed");
                Assert(Directory.GetFiles(directory, "pre-recovery-*.json").Length == 1, "corrupt_original_not_retained");
            });
            host = new Child("serve", "--workspace", workspace, "--seconds", "3", "--session-seconds", "1");
            await host.Ready();
            using var recovered = new Client(host.Port);
            await Check("recovered_data_and_session_expiration", async () =>
            {
                var session = await recovered.Send(new { op = "session.open", profileUid = account });
                token = session.GetProperty("session").GetString()!;
                var data = await recovered.Send(Read());
                Assert(data.GetProperty("revision").GetInt64() == 2 && data.GetProperty("equipment").GetArrayLength() == 4, "recovery_readback_mismatch");
                await Task.Delay(1200);
                await recovered.Send(Read(), "expired_session");
            });
            await Check("bounded_runtime_clean_exit", async () => Assert(await host.Exit() == 0, "normal_exit_failed"));
            host.Dispose(); host = null;
            await Check("foreign_paths_refused", async () =>
            {
                using var outside = new Child("init", "--workspace", "..\\..\\capture");
                Assert(await outside.Exit() == 2, "outside_path_accepted");
            });
        }
        catch (Exception e) { failures++; Steps.Add(new { step = "integration_setup_or_sequence", passed = false, detail = e.Message }); }
        finally { host?.Dispose(); }
        Directory.CreateDirectory(Path.GetDirectoryName(report)!);
        var result = new { version = 1, scope = "GPW_OWN_SERVICE_SYNTHETIC_DATA", gameRuntimeVerified = false,
            passed = Steps.Count - failures, failed = failures, workspace, executableSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Assembly.GetExecutingAssembly().Location))), steps = Steps };
        File.WriteAllBytes(report, JsonSerializer.SerializeToUtf8Bytes(result, Json.Options));
        Program.Output(result);
        return failures == 0 ? 0 : 1;
    }
}
