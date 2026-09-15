#!/usr/bin/env python3
"""List the export symbols of a Windows DLL by parsing the PE export table.

Zero dependencies (hand-rolled PE parsing, no pefile needed). It can enumerate
the exported VS C API symbols of `carsim_64.dll` and works for any DLL.

Usage:  python dump_dll_exports.py <path-to.dll> [more.dll ...]
"""
import struct
import sys


def exports(path):
    with open(path, 'rb') as f:
        data = f.read()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    assert data[pe:pe + 4] == b'PE\0\0'
    nsec = struct.unpack_from('<H', data, pe + 6)[0]
    optsz = struct.unpack_from('<H', data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from('<H', data, opt)[0]
    dd = opt + (112 if magic == 0x20b else 96)   # PE32+ vs PE32 data dir
    exp_rva, exp_sz = struct.unpack_from('<II', data, dd)
    if not exp_rva:
        return []
    sec = opt + optsz
    secs = []
    for i in range(nsec):
        s = data[sec + i * 40:sec + i * 40 + 40]
        va, sz = struct.unpack_from('<I', s, 12)[0], struct.unpack_from('<I', s, 8)[0]
        raw = struct.unpack_from('<I', s, 20)[0]
        secs.append((va, sz, raw))

    def r2o(rva):                                  # RVA -> file offset
        for va, sz, raw in secs:
            if va <= rva < va + max(sz, 1):
                return raw + (rva - va)
        return None

    o = r2o(exp_rva)
    nnames = struct.unpack_from('<I', data, o + 24)[0]
    names_rva = struct.unpack_from('<I', data, o + 32)[0]
    no = r2o(names_rva)
    out = []
    for i in range(nnames):
        nrva = struct.unpack_from('<I', data, no + 4 * i)[0]
        p = r2o(nrva)
        out.append(data[p:data.index(b'\0', p)].decode())
    return out


if __name__ == '__main__':
    for dll in sys.argv[1:]:
        print('==', dll)
        try:
            ex = exports(dll)
            print(len(ex), 'exports')
            for e in sorted(ex):
                print(' ', e)
        except Exception as exc:
            print('ERR', exc)
