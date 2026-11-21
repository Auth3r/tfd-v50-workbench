using System;
using System.ComponentModel;
using System.Collections.Generic;
using System.Runtime.InteropServices;

// Windows Filtering Platform user-mode API, x64. Every block is scoped to the
// application ID of one of the two game images. A dynamic session owns all IDs.
public sealed class GpwEgress : IDisposable {
    [StructLayout(LayoutKind.Sequential)] struct Display { public IntPtr name, description; }
    [StructLayout(LayoutKind.Sequential)] struct Session {
        public Guid key; public Display display; public uint flags, timeout, pid;
        public IntPtr sid, user; public int kernel;
    }
    [StructLayout(LayoutKind.Sequential)] struct Blob { public uint size; public IntPtr data; }
    [StructLayout(LayoutKind.Sequential)] struct Value {
        public uint type; public UIntPtr value;
        public Value(uint type, ulong n) { this.type = type; value = new UIntPtr(n); }
    }
    [StructLayout(LayoutKind.Sequential)] struct Condition {
        public Guid field; public uint match; public Value value;
        public Condition(Guid key, uint op, Value v) { field = key; match = op; value = v; }
    }
    [StructLayout(LayoutKind.Sequential)] struct Action { public uint type; public Guid key; }
    [StructLayout(LayoutKind.Sequential)] struct Filter {
        public Guid key; public Display display; public uint flags; public IntPtr provider;
        public Blob data; public Guid layer, sublayer; public Value weight;
        public uint count; public IntPtr conditions; public Action action;
        public ulong contextLow, contextHigh; public IntPtr reserved;
        public ulong id; public Value effectiveWeight;
    }
    const string Dll = "fwpuclnt.dll";
    [DllImport(Dll)] static extern uint FwpmEngineOpen0(IntPtr server, uint auth, IntPtr identity, ref Session session, out IntPtr engine);
    [DllImport(Dll)] static extern uint FwpmEngineClose0(IntPtr engine);
    [DllImport(Dll)] static extern uint FwpmTransactionBegin0(IntPtr engine, uint flags);
    [DllImport(Dll)] static extern uint FwpmTransactionCommit0(IntPtr engine);
    [DllImport(Dll, CharSet=CharSet.Unicode, ExactSpelling=true)] static extern uint FwpmGetAppIdFromFileName0(string file, out IntPtr blob);
    [DllImport(Dll)] static extern void FwpmFreeMemory0(ref IntPtr p);
    [DllImport(Dll)] static extern uint FwpmFilterAdd0(IntPtr engine, ref Filter filter, IntPtr sd, out ulong id);
    [DllImport(Dll)] static extern uint FwpmFilterGetById0(IntPtr engine, ulong id, out IntPtr filter);

    static readonly Guid V4 = new Guid("c38d57d1-05a7-4c33-904f-7fbceee60e82");
    static readonly Guid V6 = new Guid("4a72393b-319f-44bc-84c3-ba54dcb3b6b4");
    static readonly Guid Universal = new Guid("eebecc03-ced4-4380-819a-2734397b2b74");
    static readonly Guid App = new Guid("d78e1e87-8644-4ea5-9437-d809ecefc971");
    static readonly Guid Address = new Guid("b235ae9a-1d64-49b8-a44c-5ff3d9095045");
    static readonly Guid Protocol = new Guid("3971ef2b-623e-4f9a-8cb1-6e79b806b9a7");
    static readonly Guid Port = new Guid("c35a604d-d22b-4e1a-91b4-68f674ee674b");
    const uint Equal = 0, Greater = 1, Less = 2, NotEqual = 10, UInt8 = 1, UInt16 = 2, UInt32 = 3, ByteBlob = 12;
    IntPtr handle;
    readonly List<ulong> filters = new List<ulong>();
    public ulong[] FilterIds { get { return filters.ToArray(); } }

    static void Check(uint status, string operation) {
        if (status != 0) throw new Win32Exception(unchecked((int)status), operation + ": 0x" + status.ToString("X8"));
    }
    public GpwEgress(string[] images, ushort port) {
        if (port == 0 || port == ushort.MaxValue) throw new ArgumentOutOfRangeException("port");
        var session = new Session { flags = 1 }; // FWPM_SESSION_FLAG_DYNAMIC
        Check(FwpmEngineOpen0(IntPtr.Zero, 10, IntPtr.Zero, ref session, out handle), "engine open");
        try {
            Check(FwpmTransactionBegin0(handle, 0), "begin");
            foreach (string path in images) {
                IntPtr blob;
                Check(FwpmGetAppIdFromFileName0(path, out blob), "app ID");
                try {
                    var app = new Condition(App, Equal, new Value(ByteBlob, unchecked((ulong)blob.ToInt64())));
                    Add(V6, app);
                    Add(V4, app, new Condition(Address, NotEqual, new Value(UInt32, 0x7f000001)));
                    Add(V4, app, new Condition(Protocol, NotEqual, new Value(UInt8, 6)));
                    // Two adjacent reserved ports, Login then Client. Every other port is blocked.
                    Add(V4, app, new Condition(Port, Less, new Value(UInt16, port)));
                    Add(V4, app, new Condition(Port, Greater, new Value(UInt16, (uint)port + 1)));
                } finally { FwpmFreeMemory0(ref blob); }
            }
            Check(FwpmTransactionCommit0(handle), "commit");
            foreach (ulong id in filters) {
                IntPtr f;
                Check(FwpmFilterGetById0(handle, id, out f), "filter readback");
                FwpmFreeMemory0(ref f);
            }
        } catch { Dispose(); throw; }
    }
    void Add(Guid layer, params Condition[] conditions) {
        var pin = GCHandle.Alloc(conditions, GCHandleType.Pinned);
        var name = Marshal.StringToHGlobalUni("GPW local game session");
        try {
            var f = new Filter {
                layer = layer, sublayer = Universal, display = new Display { name = name },
                count = (uint)conditions.Length, conditions = pin.AddrOfPinnedObject(),
                action = new Action { type = 0x1001 } // FWP_ACTION_BLOCK
            };
            ulong id;
            Check(FwpmFilterAdd0(handle, ref f, IntPtr.Zero, out id), "add block");
            filters.Add(id);
        } finally { Marshal.FreeHGlobal(name); pin.Free(); }
    }
    public void Dispose() {
        if (handle != IntPtr.Zero) {
            Check(FwpmEngineClose0(handle), "close engine");
            handle = IntPtr.Zero;
        }
    }
}
