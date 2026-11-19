# v3 consistency check

resolved 228 / 300

## status by section

| section | strong | good | weak | poor | no_seed_hit | bad_rva |
|---|---|---|---|---|---|---|
| .text | 3 | 192 | 33 | 39 | 2 | 0 |
| .rdata | 0 | 0 | 0 | 0 | 26 | 0 |
| .data | 0 | 0 | 0 | 0 | 2 | 1 |
| ? | 0 | 0 | 0 | 0 | 0 | 2 |

## monotonicity violations (suspect mismatches)

count: 41

- 0x369c010 .text delta 0x31900 new 0x36cd910 score 0.9141 (good)
- 0x369c1e0 .text delta 0x31900 new 0x36cdae0 score 0.9746 (good)
- 0x369c2d0 .text delta 0x31900 new 0x36cdbd0 score 0.9707 (good)
- 0x369c550 .text delta 0x31900 new 0x36cde50 score 0.9316 (good)
- 0x369ca60 .text delta 0x31900 new 0x36ce360 score 0.9707 (good)
- 0x369cce0 .text delta 0x31900 new 0x36ce5e0 score 0.9707 (good)
- 0x36c26b0 .text delta 0x101a0 new 0x36d2850 score 0.7578 (weak)
- 0x36c2a30 .text delta 0xfe20 new 0x36d2850 score 0.752 (weak)
- 0x36c3280 .text delta 0x30990 new 0x36f3c10 score 0.9727 (good)
- 0x36c86c0 .text delta 0xa190 new 0x36d2850 score 0.752 (weak)
- 0x36d9c50 .text delta 0x-7050 new 0x36d2c00 score 0.9297 (good)
- 0x36da630 .text delta 0x-7de0 new 0x36d2850 score 0.7988 (weak)
- 0x36fdff0 .text delta 0x-35530 new 0x36c8ac0 score 0.9199 (good)
- 0x3be07a0 .text delta 0x57a50 new 0x3c381f0 score 0.9238 (good)
- 0x3c311d0 .text delta 0x5ca50 new 0x3c8dc20 score 0.9219 (good)
- 0x3c3b910 .text delta 0x5ca70 new 0x3c98380 score 0.8535 (weak)
- 0x3c3f670 .text delta 0x23e40 new 0x3c634b0 score 0.9473 (good)
- 0x3c42b20 .text delta 0x-1c970 new 0x3c261b0 score 0.7637 (weak)
- 0x3c7d270 .text delta 0x5aee0 new 0x3cd8150 score 0.9219 (good)
- 0x3c842a0 .text delta 0x5aee0 new 0x3cdf180 score 0.9746 (good)
- 0x3dc2090 .text delta 0x51c10 new 0x3e13ca0 score 0.9473 (good)
- 0x3dd8210 .text delta 0x52fa0 new 0x3e2b1b0 score 0.9395 (good)
- 0x3e8c490 .text delta 0x55d40 new 0x3ee21d0 score 0.9551 (good)
- 0x3f97720 .text delta 0x63b80 new 0x3ffb2a0 score 0.9434 (good)
- 0x3fba2d0 .text delta 0x63160 new 0x401d430 score 0.9434 (good)

## new-address collisions

- 0x36d2850 <- 0x36c26b0, 0x36c2a30, 0x36c86c0, 0x36da630
- 0x44e1180 <- 0x4440550, 0x4440880

## unresolved (with neighbour-based prediction)

- 0x34f34a0 .text status poor prev_delta 0x30100 next_delta 0x33980 predicted 0x35235a0
- 0x3641950 .text status poor prev_delta 0x33980 next_delta 0x31900 predicted 0x36752d0
- 0x369cf70 .text status poor prev_delta 0x31900 next_delta 0x31b20 predicted 0x36ce870
- 0x36a5030 .text status poor prev_delta 0x324d0 next_delta 0x324d0 predicted 0x36d7500
- 0x36be670 .text status poor prev_delta 0x32750 next_delta 0x32750 predicted 0x36f0dc0
- 0x36be870 .text status poor prev_delta 0x32750 next_delta 0x32750 predicted 0x36f0fc0
- 0x36beb60 .text status poor prev_delta 0x32750 next_delta 0x32830 predicted 0x36f12b0
- 0x36c6970 .text status poor prev_delta 0x30990 next_delta 0x32f80 predicted 0x36f7300
- 0x36c8a60 .text status poor prev_delta 0xa190 next_delta 0x32f80 predicted 0x36d2bf0
- 0x36d20e0 .text status poor prev_delta 0x32f80 next_delta 0x-7050 predicted 0x3705060
- 0x36e6810 .text status poor prev_delta 0x348d0 next_delta 0x346a0 predicted 0x371b0e0
- 0x36ed580 .text status poor prev_delta 0x346a0 next_delta 0x346a0 predicted 0x3721c20
- 0x36f2710 .text status poor prev_delta 0x34690 next_delta 0x341b0 predicted 0x3726da0
- 0x36f2b60 .text status poor prev_delta 0x34690 next_delta 0x341b0 predicted 0x37271f0
- 0x36fbc30 .text status poor prev_delta 0x341a0 next_delta 0x-35530 predicted 0x372fdd0
- 0x36fbe10 .text status poor prev_delta 0x341a0 next_delta 0x-35530 predicted 0x372ffb0
- 0x38ff0c0 .text status poor prev_delta 0x-35530 next_delta 0x47fd0 predicted 0x38c9b90
- 0x3900a10 .text status poor prev_delta 0x-35530 next_delta 0x47fd0 predicted 0x38cb4e0
- 0x40d19a0 .text status poor prev_delta 0x73020 next_delta 0x5bc20 predicted 0x41449c0
- 0x40d242c .text status no_seed_hit prev_delta 0x73020 next_delta 0x5bc20 predicted 0x414544c
- 0x40d2bf4 .text status poor prev_delta 0x73020 next_delta 0x5bc20 predicted 0x4145c14
- 0x40d2c66 .text status poor prev_delta 0x73020 next_delta 0x5bc20 predicted 0x4145c86
- 0x422f390 .text status poor prev_delta 0x98480 next_delta 0x98480 predicted 0x42c7810
- 0x4248900 .text status poor prev_delta 0x98860 next_delta 0x98970 predicted 0x42e1160
- 0x43ecd50 .text status poor prev_delta 0x97600 next_delta 0x9f8d0 predicted 0x4484350
- 0x43ed2b0 .text status poor prev_delta 0x97600 next_delta 0x9f8d0 predicted 0x44848b0
- 0x4434820 .text status poor prev_delta 0xa0430 next_delta 0xa0dd0 predicted 0x44d4c50
- 0x4434e10 .text status poor prev_delta 0xa0430 next_delta 0xa0dd0 predicted 0x44d5240
- 0x44354b0 .text status poor prev_delta 0xa0430 next_delta 0xa0dd0 predicted 0x44d58e0
- 0x44358e0 .text status poor prev_delta 0xa0430 next_delta 0xa0dd0 predicted 0x44d5d10
- 0x4436020 .text status poor prev_delta 0xa0430 next_delta 0xa0dd0 predicted 0x44d6450
- 0x443f370 .text status poor prev_delta 0xa1000 next_delta 0xa0c30 predicted 0x44e0370
- 0x443f430 .text status poor prev_delta 0xa1000 next_delta 0xa0c30 predicted 0x44e0430
- 0x44489f0 .text status poor prev_delta 0xa0da0 next_delta 0xa0e10 predicted 0x44e9790
- 0x4459f40 .text status poor prev_delta 0xa3040 next_delta 0xa2260 predicted 0x44fcf80
- 0x449f5c0 .text status no_seed_hit prev_delta 0xa20d0 next_delta 0xa2370 predicted 0x4541690
- 0x449fcb0 .text status poor prev_delta 0xa20d0 next_delta 0xa2370 predicted 0x4541d80
- 0x44a01e0 .text status poor prev_delta 0xa20d0 next_delta 0xa2370 predicted 0x45422b0
- 0x44a0730 .text status poor prev_delta 0xa20d0 next_delta 0xa2370 predicted 0x4542800
- 0x44a1280 .text status poor prev_delta 0xa2370 next_delta 0xa2360 predicted 0x45435f0
- 0x49cdbf0 .text status poor prev_delta 0xd5ac0 next_delta 0xd5680 predicted 0x4aa36b0
- 0x8fc0930 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x909f640
- 0x9658ab0 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x97377c0
- 0x9803f50 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x98e2c60
- 0x98f78e8 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x99d65f8
- 0x99241f0 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9a02f00
- 0x9942950 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9a21660
- 0x9a4d138 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b2be48
- 0x9a548e8 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b335f8
- 0x9a60570 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b3f280
- 0x9a63a98 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b427a8
- 0x9a64528 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b43238
- 0x9a67848 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b46558
- 0x9a67fc8 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b46cd8
- 0x9a69ce8 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b489f8
- 0x9a6ea68 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b4d778
- 0x9a6f3b8 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b4e0c8
- 0x9a776b8 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b563c8
- 0x9a781f0 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b56f00
- 0x9a7f160 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b5de70
- 0x9a83d88 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b62a98
- 0x9a85e78 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b64b88
- 0x9a86308 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b65018
- 0x9a8afe0 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b69cf0
- 0x9a8cfd0 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b6bce0
- 0x9a8f260 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0x9b6df70
- 0xa0c4948 .rdata status no_seed_hit prev_delta 0xded10 next_delta None predicted 0xa1a3658
- 0xb75c300 .data status no_seed_hit prev_delta 0xded10 next_delta None predicted 0xb83b010
- 0xb75c314 .data status no_seed_hit prev_delta 0xded10 next_delta None predicted 0xb83b024
- 0xbcbb2b0 .data status bad_rva prev_delta 0xded10 next_delta None predicted 0xbd99fc0
- 0x30200000 ? status bad_rva prev_delta 0xded10 next_delta None predicted 0x302ded10
- 0x60000030 ? status bad_rva prev_delta 0xded10 next_delta None predicted 0x600ded40
