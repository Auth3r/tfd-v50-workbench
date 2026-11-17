using System.Security.Cryptography;
using System.Text.Json;

namespace GpwOffline;

public static class Program
{
    public static async Task<int> Main(string[] args)
    {
        try
        {
            if (args.Length == 0 || args[0] == "--help")
            {
                Console.WriteLine("GPW Offline by 狗屁王_official\n本项目不是 NEXON 官方软件，与游戏开发商和发行商无隶属关系。\n");
                Console.WriteLine("Independent local equipment/save core. L1 only; no verified game wire adapter or playable world.");
                Console.WriteLine("init --workspace NAME\nserve --workspace NAME --seconds 60 [--port 0] [--session-seconds 300] [--allow-provisioning]\nrecovery-info --workspace NAME\nrecover-previous --workspace NAME --generation N\ninspect --workspace NAME\nidentify --game-root PATH\n--self-test REPORT.json");
                return 0;
            }
            if (args[0] == "--self-test" && args.Length == 2) return await SelfTest.Run(args[1]);
            if (args[0] == "--screenshot") throw new CoreFault("headless_core_has_no_game_or_gui_screenshot");
            var options = Parse(args.Skip(1).ToArray());
            switch (args[0])
            {
                case "init":
                    Only(options, "workspace");
                    using (var store = new Persistence(Required(options, "workspace"), initialize: true))
                        Output(new { initialized = true, format = store.State.Format });
                    break;
                case "serve":
                    Only(options, "workspace", "seconds", "port", "session-seconds", "allow-provisioning");
                    var seconds = Number(options, "seconds", null, 1, 3600);
                    var port = Number(options, "port", 0, 0, 65535);
                    var ttl = Number(options, "session-seconds", 300, 1, 3600);
                    using (var store = new Persistence(Required(options, "workspace")))
                        await Server.Run(new LocalService(store, options.ContainsKey("allow-provisioning"), TimeSpan.FromSeconds(ttl)), port, seconds);
                    break;
                case "recover-previous":
                    Only(options, "workspace", "generation");
                    if (!long.TryParse(Required(options, "generation"), out var generation) || generation < 0) throw new CoreFault("invalid_generation");
                    using (var store = new Persistence(Required(options, "workspace"), recovery: true)) Output(store.RecoverPrevious(generation));
                    break;
                case "recovery-info":
                    Only(options, "workspace");
                    using (var store = new Persistence(Required(options, "workspace"), recovery: true)) Output(store.DescribePrevious());
                    break;
                case "inspect":
                    Only(options, "workspace");
                    using (var store = new Persistence(Required(options, "workspace")))
                        Output(new { store.State.Format, store.State.Generation, profiles = store.State.Profiles.Count,
                            equipment = store.State.Profiles.Values.Sum(p => p.Equipment.Count), integrity = "verified", gameSaveCompatible = false });
                    break;
                case "identify":
                    Only(options, "game-root");
                    Identify(Required(options, "game-root"));
                    break;
                default: throw new CoreFault("unknown_command");
            }
            return 0;
        }
        catch (Exception e) when (e is CoreFault or IOException or UnauthorizedAccessException or JsonException or ArgumentException)
        {
            // Do not echo tokens, request bodies, private paths, or raw exceptions.
            Output(new { error = e is CoreFault f ? f.Code : "local_io_or_input_error" });
            return 2;
        }
    }

    private static Dictionary<string, string> Parse(string[] args)
    {
        var result = new Dictionary<string, string>();
        for (var i = 0; i < args.Length; i++)
        {
            if (!args[i].StartsWith("--", StringComparison.Ordinal)) throw new CoreFault("invalid_option");
            var key = args[i][2..];
            var value = key == "allow-provisioning" ? "true" : ++i < args.Length ? args[i] : throw new CoreFault("option_value_required");
            if (!result.TryAdd(key, value)) throw new CoreFault("duplicate_option");
        }
        return result;
    }
    private static void Only(Dictionary<string, string> options, params string[] keys)
    {
        if (options.Keys.Any(k => !keys.Contains(k))) throw new CoreFault("unknown_option");
    }
    private static string Required(Dictionary<string, string> options, string key) => options.TryGetValue(key, out var value) ? value : throw new CoreFault("required_option_missing");
    private static int Number(Dictionary<string, string> options, string key, int? fallback, int min, int max)
    {
        var text = options.TryGetValue(key, out var supplied) ? supplied : fallback?.ToString();
        if (!int.TryParse(text, out var n) || n < min || n > max) throw new CoreFault("invalid_numeric_option");
        return n;
    }
    public static void Output(object value) => Console.WriteLine(JsonSerializer.Serialize(value, Json.Options));

    private static void Identify(string root)
    {
        var identities = new[]
        {
            (Relative: "M1/Binaries/Win64/M1-Win64-Shipping.exe", Sha: "c01476888da891bf38f464aca7081a7da6bde6a33e50485cd75c9fa93794e867"),
            (Relative: "TheFirstDescendant.exe", Sha: "88793f25b554b7a72b93aaa239d796b82ee192f7f7bf31d58355c913648734d1")
        };
        var result = identities.Select(identity =>
        {
            var path = Paths.Within(Path.Combine(root, identity.Relative.Replace('/', Path.DirectorySeparatorChar)), root);
            using var file = File.OpenRead(path);
            var hash = Convert.ToHexString(SHA256.HashData(file)).ToLowerInvariant();
            return new { file = identity.Relative, sha256 = hash, matchesResearchBuild = hash == identity.Sha };
        }).ToArray();
        Output(new { files = result, knownFilePair = result.All(f => f.matchesResearchBuild), supportedGameProtocol = false,
            supportedLaunchEntry = "unknown", gameExecuted = false });
    }
}
