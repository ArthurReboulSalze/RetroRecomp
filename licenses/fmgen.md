# FMGEN (YM2151 OPM sound generator)

FM Sound Generator with OPN/OPM interface, copyright (C) cisc 1998, 2003
(cisc@retropc.net). Used by the experimental Sharp X68000 runtime for the
YM2151 (OPM) only, from the copy in hissorii/px68k
[`74ddbb3`](https://github.com/hissorii/px68k/tree/74ddbb37b4e12b77362a4e12f28ceb5aaa593684/fmgen): `fmgen.cpp`, `fmtimer.cpp`, `opm.cpp`,
`fmg_wrap.cpp` and their headers. The OPN/PSG parts and the Mercury Unit
(YMF288) wrapper are not compiled.

## Terms (informal English summary; the Japanese text below is authoritative)

- Copyright stays with the author; the source is provided as is, without any
  warranty, and the author is not liable for any damage.
- It may be freely modified, embedded, distributed and used, provided that:
  1. its origin (author, copyright) is stated;
  2. distribution is as free software;
  3. modified source states its modifications;
  4. distributed source carries this text unmodified.
- Contacting the author on publication is appreciated (not required).
- Embedding any part in commercial software (shareware included) requires the
  author's prior agreement. Retro-Recomp is noncommercial.

## Modifications made by Retro-Recomp

Applied to build copies by `tools/x68000_base74.py`; the pinned sources are not
changed and the repository does not redistribute them.

- `opm.cpp`, `opm.h`: the LFO noise uses a deterministic generator owned by the
  chip (`rr_lfo_random`) instead of the C library `rand()`, and `Reset()`
  clears the LFO counters.
- `fmg_wrap.cpp`: the Mercury Unit (YMF288) wrapper is removed; the OPM wrapper
  initialises and resets its register latch and count.
- `fmgen.h`, `opm.h`, `fmtimer.h`, `fmg_wrap.cpp`: a snapshot serializer
  (Retro-Recomp, MIT) is appended and declared a friend of the chip classes.

## Original text (`fmgen/readme.txt`, EUC-JP, 3177 bytes, SHA-256 `154eb685bd11418c7390f72eb6fded9c1e0630b4f677983a47dff0e421fb3628`)

Transcoded to UTF-8 without other change.

```
------------------------------------------------------------------------------
        FM Sound Generator with OPN/OPM interface
        Copyright (C) by cisc 1998, 2003.
------------------------------------------------------------------------------

【概要】
	C++ による FM/PSG 音源の実装です。
	
	AY8910, YM2203, YM2151, YM2608, YM2610 相当のインターフェースも
	実装してあります。


【使い方】
	(TODO:中身を書く)

【注意】
	以前のバージョンから幾分手を加えました。インターフェースは
	いじっていないつもりですが、何かしらのバグが隠れているかもしれません。

	YM2610 は動作チェックすらしていません。

	線形補完モード(interpolation)は廃止されました。
	Init() の引数仕様は変わっていませんが、interpolation = true にしても
	動作は変わりません。

	OPNA::Init/SetRate で与えるチップクロックの値の仕様が
	以前の M88 に搭載されていたバージョンと異なっています．


【著作権、免責規定】

	・本ソースコードは作者(cisc@retropc.net) が著作権を所有しています。
	
	・本ソースコードはあるがままに提供されるものであり，
	  暗黙及び明示的な保証を一切含みません．
	  
	・本ソースコードを利用したこと，利用しなかったこと，
	  利用できなかったことに関して生じたあるいは生じると予測される
	  損害について，作者は一切責任を負いません．
	  
	・本ソースコードは，以下の制限を満たす限り自由に改変・組み込み・
	  配布・利用することができます．
	  
	  1. 本ソフトの由来(作者, 著作権)を明記すること.
	  2. 配布する際にはフリーソフトとすること．
	  3. 改変したソースコードを配布する際は改変内容を明示すること.
	  4. ソースコードを配布する際にはこのテキストを一切改変せずに
	     そのまま添付すること．
	  
	・公開の際に作者への連絡を頂ければ幸いです．
	
	・商用ソフト(シェアウェア含む) に本ソースコードの一部，または
	  全部を組み込む際には，事前に作者の合意を得る必要があります．


【変更点】
008	030902	・出力サンプリングレートの設定を、チップ元来の合成サンプ
                  リングレートと異なる設定にするとエンベロープがおかしく
                  なる問題を修正。

007a	030608	・領域外アクセスがあったのを修正 (Thanks to ＰＩ．様)

007	030607	・再現性の向上
		・OPN: SSG-EG のサポート
		・線形補完の廃止
		・asm 版の廃止
		・マルチスレッドフリーになった？

006	010330	・再現性に関していくらか手直し(正弦波，出力タイミング等)

005	010317	・OPN: FM 音源の合成周波数が出力周波数よりも低いときに，
		  補完を使うと音痴になる/音がまともに出なくなる問題を修正.
		・FM: 補完を使わない時の精度を上げてみる．
		  問題が起きたら fmgeninl.h の FM_RATIOBITS を 8 に戻すと吉．

004a	010311	・OPM: ノイズをそこそこ聞けるレベル(？)まで修正.
		・OPNA/OPM: FM_USE_CALC2 廃止.
		・デグレ修正, なんのために cvs で管理しているんだか…(T-T
		  OPNB: ADPCMB ROM マスク作成ミス.
		  OPNB: ADPCMA ステータスフラグ関係の挙動修復.
		  OPM: LFO パラメータの初期化を忘れていたのを修正.

003	010124	・OPNA/OPM： 実際には補完前の値を出力していたバグを修正.

002	010123	・合成周波数が出力周波数より低いときでも補間が効くようにする.
		・OPN: 補間時にプリスケーラの設定を変更したときに音化けする
		  バグを修正.
		・OPNA/B: LFO が効かないバグを修正.

001 	000928	・初期バージョン


$fmgen-Id: readme.txt,v 1.1 2003/06/07 08:25:20 cisc Exp $
```
