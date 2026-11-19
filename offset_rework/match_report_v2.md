# anchor match pass 2 (multi-seed vote + 512B verify)

old: E:\第二后裔\The First Descendant\M1\Binaries\Win64\M1-Win64-Shipping.exe
new: F:\Codex\TFD-Zero-P0\build-26722146\runtime-copy\M1\Binaries\Win64\M1-Win64-Shipping.exe

summary: {"anchors": 43, "strong": 2, "good": 23, "weak": 3, "poor": 4, "no_seed_hit": 10, "bad_rva": 1}

## delta clusters

| delta | count | members |
|---|---|---|
| 0xa2270 | 5 | 0x4471b50, 0x4471c70, 0x4472c00, 0x4472d30, 0x4476e80 |
| 0xa2260 | 3 | 0x446f260, 0x44703a0, 0x4471460 |
| 0x64310 | 2 | 0x40a0f90, 0x40a2290 |
| 0x97210 | 2 | 0x41cdbe0, 0x41ce9c0 |
| 0xa03d0 | 2 | 0x441b2c0, 0x441b2d0 |
| 0xa0da0 | 2 | 0x4445e70, 0x4445e80 |
| 0xe4310 | 2 | 0x51d3f10, 0x51f1100 |

## anchors

| old RVA | status | new RVA | delta | score | votes | js lines |
|---|---|---|---|---|---|---|
| 0x3641950 | poor | 0x2f56ec9 | 0x-6eaa87 | 0.1934 | 1 | 611 |
| 0x36db250 | poor | 0x1317956 | 0x-23c38fa | 0.1836 | 3 | 2033 |
| 0x3ba90c0 | good | 0x3c25e20 | 0x7cd60 | 0.9453 | 3 | 1660 |
| 0x3c3f670 | poor | 0x3c61650 | 0x21fe0 | 0.2949 | 3 | 603 |
| 0x3e8c490 | good | 0x3ee21d0 | 0x55d40 | 0.9551 | 6 | 657 |
| 0x40a0f90 | strong | 0x41052a0 | 0x64310 | 1.0 | 6 | 607 |
| 0x40a2290 | strong | 0x41065a0 | 0x64310 | 1.0 | 5 | 605 |
| 0x4164dc0 | good | 0x41fa6d0 | 0x95910 | 0.9473 | 5 | 615 |
| 0x41cdbe0 | good | 0x4264df0 | 0x97210 | 0.9004 | 4 | 1982 |
| 0x41ce9c0 | good | 0x4265bd0 | 0x97210 | 0.9688 | 4 | 1654 |
| 0x422f6f0 | good | 0x42c7b70 | 0x98480 | 0.9688 | 4 | 1082 |
| 0x4236d90 | poor | 0x24584b0 | 0x-1dde8e0 | 0.5 | 2 | 1095 |
| 0x43fd5a0 | good | 0x449d540 | 0x9ffa0 | 0.9062 | 4 | 534,699,1116 |
| 0x441b2c0 | good | 0x44bb690 | 0xa03d0 | 0.9277 | 3 | 544 |
| 0x441b2d0 | good | 0x44bb6a0 | 0xa03d0 | 0.9277 | 5 | 492 |
| 0x441f8a0 | good | 0x44bfc80 | 0xa03e0 | 0.9355 | 2 | 490,601,794 |
| 0x4445e70 | good | 0x44e6c10 | 0xa0da0 | 0.9316 | 3 | 715 |
| 0x4445e80 | good | 0x44e6c20 | 0xa0da0 | 0.9316 | 4 | 609 |
| 0x4454710 | good | 0x44f7750 | 0xa3040 | 0.9102 | 4 | 1662 |
| 0x446f260 | good | 0x45114c0 | 0xa2260 | 0.9121 | 3 | 1706 |
| 0x44703a0 | good | 0x4512600 | 0xa2260 | 0.9141 | 4 | 1728 |
| 0x4471460 | good | 0x45136c0 | 0xa2260 | 0.9414 | 3 | 1894 |
| 0x4471b50 | good | 0x4513dc0 | 0xa2270 | 0.9082 | 2 | 1864 |
| 0x4471c70 | weak | 0x4513ee0 | 0xa2270 | 0.8633 | 4 | 1656,1692 |
| 0x4472c00 | weak | 0x4514e70 | 0xa2270 | 0.8887 | 2 | 1648 |
| 0x4472d30 | weak | 0x4514fa0 | 0xa2270 | 0.8477 | 2 | 1650 |
| 0x4476e80 | good | 0x45190f0 | 0xa2270 | 0.9277 | 2 | 2033 |
| 0x44b9720 | good | 0x455ba70 | 0xa2350 | 0.9434 | 2 | 792,1644,2030 |
| 0x44c1700 | good | 0x4563ca0 | 0xa25a0 | 0.957 | 4 | 1092 |
| 0x51d3f10 | good | 0x52b8220 | 0xe4310 | 0.9746 | 5 | 962,2054 |
| 0x51f1100 | good | 0x52d5410 | 0xe4310 | 0.9004 | 5 | 613 |
| 0x6ddb820 | good | 0x6ebc350 | 0xe0b30 | 0.9297 | 2 | 796,1658,2032 |
| 0x8fc0930 | no_seed_hit |  |  |  |  | 1096 |
| 0x9803f50 | no_seed_hit |  |  |  |  | 1988 |
| 0x9a60570 | no_seed_hit |  |  |  |  | 918 |
| 0x9a64528 | no_seed_hit |  |  |  |  | 798 |
| 0x9a6f3b8 | no_seed_hit |  |  |  |  | 1814 |
| 0x9a776b8 | no_seed_hit |  |  |  |  | 2033 |
| 0x9a781f0 | no_seed_hit |  |  |  |  | 1666,1776,1904 |
| 0x9a86308 | no_seed_hit |  |  |  |  | 798 |
| 0xb75c300 | no_seed_hit |  |  |  |  | 1086 |
| 0xb75c314 | no_seed_hit |  |  |  |  | 1085 |
| 0xbcbb2b0 | bad_rva |  |  |  |  | 1854 |
