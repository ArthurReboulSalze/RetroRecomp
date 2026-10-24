# Sharp X68000 machine runtime

The experimental X68000 runtime is built from
[hissorii/px68k at `74ddbb3`](https://github.com/hissorii/px68k/tree/74ddbb37b4e12b77362a4e12f28ceb5aaa593684) (2014), with no file from the later
libretro fork (`px68k-libretro`, which declares the GPL since May 2020). The
lineage is WinX68k / Keropi by Kenjo, the X11 port xkeropi by NONAKA Kimihiro,
and the SDL port PX68k by hissorii. Each build copy is checked against that
commit before Retro-Recomp's documented adaptations are applied
(`tools/x68000_base74.py`). Provenance and method:
[`native/x68000_machine/PROVENANCE.md`](../native/x68000_machine/PROVENANCE.md).

| Part | Files | Terms |
| --- | --- | --- |
| Virtual devices | `x68k/*.c` (ADPCM, BG, CRTC, DMAC, FDC, FDD, DIM/XDF/D88, GVRAM, IOC, IRQ, memory map, Mercury register decode, MFP, MIDI, palette, PIA, RTC, SASI, SCC, SCSI, SRAM, system port, TVRAM) | Kenjo's terms below, with NONAKA's and hissorii's changes |
| Display line composition, keyboard queue, mouse | `x11/windraw.c`, `x11/keyboard.c`, `x11/mouse.c` (parts) | BSD-2-Clause, NONAKA Kimihiro (below) |
| YM2151 (OPM) | `fmgen/` | [FMGEN terms](fmgen.md) |
| MC68000 core | Musashi (Geolith copy) | [MIT / BSD-3-Clause](musashi.md) |
| Host glue, snapshots, compatibility layer, build adapters | `native/x68000_machine/`, `tools/x68000_*.py` | MIT, Retro-Recomp |
| Native 68000 code generation | GenesisRecomp / m68k-recomp-core | [PolyForm Noncommercial 1.0.0](segagenesisrecomp.md) |

Not used: the original MPU core `68kem.asm` (Mike Coates and Darren Olafson)
and `windrv.c` (yamama), the two files Kenjo excludes from his terms; the OPM
code based on Jarek Burczynski's work (FMGEN is used instead); the libretro glue,
savestate system and any libretro-era change.

## hissorii's port

hissorii did not attach a separate licence to the PX68k port. Retro-Recomp uses
these changes on the same noncommercial terms as the rest of the Kenjo lineage,
as PX68k has been distributed since 2013 (the libretro core list labels it
"Custom Non-Commercial"); Retro-Recomp's own glue around it is MIT. NONAKA's files are
BSD-licensed, and Kenjo's terms allow noncommercial modification and reuse
without any obligation to contact the author.

## Kenjo's terms (informal English summary of section 4; the Japanese text is authoritative)

- Except for the files listed below, modification and reuse are free as long as
  the use is not commercial. Software derived from it has no obligation to
  publish its source, and no contact is required (though appreciated).
- Exceptions: the MPU core (Mike Coates and Darren Olafson) and `WINDRV.C`
  (yamama) require their authors' permission.
- `OPM.C` is based on Jarek Burczynski's code.
- When distributing this source code itself, distribute the archive unchanged
  as one set.
- Kenjo does not waive copyright.

## Original text (`doc/kero_src.txt`, CP932, 4938 bytes, SHA-256 `420f539bb590be8adaa2ba1403d5086ced4255bfa3b30a36ad289dbc752c8873`)

Transcoded to UTF-8 without other change.

```
===================================================================
===== けろぴー（WinX68k）ソースコードドキュメント             =====
=====                                       (c) 2000,01 Kenjo =====
===================================================================

---------------
1. これは
---------------

　X68000エミュレータ「けろぴー」（旧「WinX68k」）のソースコードに
ついてのドキュメントです。



---------------
2. ファイル構成
---------------

　Microsoft Visual C++ 6.0 ＋ NASMW で作成されています。
　ディレクトリは以下のような構造になっています（ヘッダファイルは省
略）。

  --+-- Makefile	VC++用Makeファイル
    |
    +--win32		Windows側のファイル群
    |    |
    |    +- about.c		Aboutダイアログ
    |    +- common.c		エラーダイアログなど
    |    +- cdaspi.c		ASPIによるCD-ROMアクセス
    |    +- cdctrl.c		IOCTRLによるCD-ROMアクセス
    |    +- cdrom.c		CD-ROM（SCSI IOCS フック部）
    |    +- dsound.c		DirectSound
    |    +- fileio.c		ファイルアクセス
    |    +- joystick.c		ジョイスティック入力
    |    +- keyboard.c		キーボード入力
    |    +- keyconf.c		キーコンフィグダイアログ
    |    +- mkcgrom.c		CGROM作成ルーチン
    |    +- mouse.c		マウス入力
    |    +- prop.c		設定用プロパティシート
    |    +- status.c		ステータスバー表示
    |    +- timer.c		タイマー
    |    +- windraw.c		DirectDrawによる表示ルーチン
    |    +- winui.c		メニューなどのUI関連
    |    +- winx68k.c		メイン
    |    +- winx68k.rc		リソースファイル
    |    +- adpcm.bmp		リソース用画像データなど
    |    +- opm.bmp			〃
    |    +- nekolgc.bmp			〃
    |    +- motorola.bmp		〃
    |    +- keropi.bmp			〃
    |    +- keropi.ico			〃
    |    |
    |    +- msfiles		Microsoftから提供のヘッダ／ライブラリ
    |          |
    |          +- msfiles.txt	このディレクトリ内のファイルの入手元説明
    |
    +--x68k		X68kの仮想デバイス群
    |    |
    |    +- 68kem.asm		MPUコア（Make68kで自動生成＋修正）
    |    +- comptab.asm		↑で使われるジャンプテーブル
    |    +- adpcm.c		ADPCM
    |    +- bg.c		BG/スプライト
    |    +- bg.x86		↑用のアセンブラインクルードファイル
    |    +- crtc.c		CRTC
    |    +- dmac.c		DMAC
    |    +- fdc.c		FDC
    |    +- fdd.c		FDドライブ
    |    +- gvram.c		グラフィックVRAM
    |    +- ioc.c		I/Oコントローラ
    |    +- irqh.c		IRQハンドラ
    |    +- memory.asm		メモリアクセスルーチン
    |    +- memory.c		メモリアクセス デバッグルーチン
    |    +- mercury.c		ま～きゅり～ゆにっと
    |    +- mfp.c		MFP
    |    +- midi.c		MIDIボード
    |    +- opm.c		OPM
    |    +- palette.c		パレット
    |    +- pia.c		8255（ジョイスティック用）
    |    +- rtc.c		RTC
    |    +- sasi.c		SASI
    |    +- scc.c		SCC（マウス用）
    |    +- scsi.c		SCSIボード／BIOS（SPCへのI/Oはダミー）
    |    +- sram.c		SRAM
    |    +- sysport.c		システムポート
    |    +- tvram.c		テキストVRAM
    |    +- windrv.c		yamamaさんのWindrv.sys用デバイス
    |
    +-- release		オブジェクトファイルが格納されるディレクトリ



---------------
3. コンパイル
---------------

　けろぴーをコンパイルするには、VC++とNASMWに加え、DirectX SDKが必要で
す。
　これらが正常にインストールされたマシンでDOS窓を開き、VC++とNASMWにパ
スが通った状態で、Makefile のあるディレクトリに移動し、

        nmake

で実行ファイルが作成されます。



---------------
4. 2次使用、配布条件など
---------------

　商利用しない限りにおいて、一部のファイルを除き、改変、パクりなどは自由
です。パクって作ったソフトに関してもソースコード公開の義務はありません。
連絡も不要です（でも、使ったよ～と云ってもらえると嬉しいです（笑））。

　上記の条件から外れるのは、

  1. MPUコア
     Mike Coates 氏と Darren Olafson 氏の著作物です。流用する際は、両氏
   へ連絡し、使用許可を貰って下さい。

         Mike Coates氏連絡先 : mcoates@mame.freeserve.co.uk
         Darren Olafson氏連絡先 : deo@mail.island.net

  2. WINDRV.C
     yamama氏の著作物です。流用する際は、yamama氏へ連絡し、使用許可を貰っ
   て下さい。

         yamama氏連絡先 : yamama@ps.ksky.ne.jp

　それから、OPM.Cについては、多少変数名・関数は変わっていますが、基本的に
は Jarek Burczynski氏のコードをベースにしていますので、その点ご留意いただ
ければ幸いです。

　このコード自体の配布を目的とする場合は、アーカイブの中身は変更せずに、
ワンセットで配布して下さいね。

　著作権に関しては放棄しません（国内じゃしたくてもできないけど）。が、
まぁ好きに使って下さい（笑）。



---------------
5. 最後に
---------------

　汚いっす。見苦しいっす。プログラム下手糞っす。利用価値は無いっす。それ
でもいいよ、って方はご自由にお使いください（汗。

　一番分かりづらいのは「windraw.c」周りでしょうか……。
　描画の要はほぼ全てここに集まっていますが、フラグ立てまくりで既に私にも
訳が分かりません（ぉぃ。気が向いたら整理＆ドキュメント作成でもしましょう
か……。


-----
de けんじょ
kenjo@ceres.dti.ne.jp
kenjo@retropc.net

[EOF]
```

## NONAKA Kimihiro (x11/windraw.c, x11/keyboard.c, x11/mouse.c)

Copyright years 2003 (windraw.c) and 2003, 2008 (keyboard.c, mouse.c).

```
Copyright (c) 2003 NONAKA Kimihiro
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:
1. Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```
