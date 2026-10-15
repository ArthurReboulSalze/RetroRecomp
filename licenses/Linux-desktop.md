# Linux desktop integration dependencies

Linux builds use tkinterdnd2 0.6.4 (MIT) and its bundled tkdnd 2.10.3
(Tcl/Tk-style BSD license), plus SecretStorage 3.5.0 (BSD 3-Clause) for the
desktop Secret Service. SecretStorage uses Jeepney (MIT), cryptography
(Apache 2.0 or BSD), cffi (MIT), and pycparser (BSD).

The Linux packaging script includes the complete notices distributed by each
installed Python package in `third-party-runtime/` inside the converter.
TkDND's original notice is reproduced below; each bundled Tcl source also
retains its original copyright header. Only the native Linux extension for
the current Tcl ABI is included.

Sources:
- https://github.com/Eliav2/tkinterdnd2
- https://github.com/petasis/tkdnd
- https://github.com/mitya57/secretstorage
- https://github.com/takluyver/jeepney
- https://github.com/pyca/cryptography
- https://cffi.readthedocs.io/
- https://github.com/eliben/pycparser

The full upstream TkDND license follows in the checked-in notice.

Source: https://raw.githubusercontent.com/petasis/tkdnd/6efca37a22b93b2336dc973f2b4a9ba1e3feceaf/license.terms

This software is copyrighted by:
   Georgios Petasis, Athens, Greece.
   e-mail: petasisg@yahoo.gr, petasis@iit.demokritos.gr

   Mac portions (c) 2009-2014 Kevin Walzer/WordTech Communications LLC,
   kw@codebykevin.com

The following terms apply to all files associated with the
software unless explicitly disclaimed in individual files.

The authors hereby grant permission to use, copy, modify, distribute,
and license this software and its documentation for any purpose, provided
that existing copyright notices are retained in all copies and that this
notice is included verbatim in any distributions. No written agreement,
license, or royalty fee is required for any of the authorized uses.
Modifications to this software may be copyrighted by their authors
and need not follow the licensing terms described here, provided that
the new terms are clearly indicated on the first page of each file where
they apply.

IN NO EVENT SHALL THE AUTHORS OR DISTRIBUTORS BE LIABLE TO ANY PARTY
FOR DIRECT, INDIRECT, SPECIAL, INCIDENTAL, OR CONSEQUENTIAL DAMAGES
ARISING OUT OF THE USE OF THIS SOFTWARE, ITS DOCUMENTATION, OR ANY
DERIVATIVES THEREOF, EVEN IF THE AUTHORS HAVE BEEN ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.

THE AUTHORS AND DISTRIBUTORS SPECIFICALLY DISCLAIM ANY WARRANTIES,
INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT.  THIS SOFTWARE
IS PROVIDED ON AN "AS IS" BASIS, AND THE AUTHORS AND DISTRIBUTORS HAVE
NO OBLIGATION TO PROVIDE MAINTENANCE, SUPPORT, UPDATES, ENHANCEMENTS, OR
MODIFICATIONS.

GOVERNMENT USE: If you are acquiring this software on behalf of the
U.S. government, the Government shall have only "Restricted Rights"
in the software and related documentation as defined in the Federal 
Acquisition Regulations (FARs) in Clause 52.227.19 (c) (2).  If you
are acquiring the software on behalf of the Department of Defense, the
software shall be classified as "Commercial Computer Software" and the
Government shall have only "Restricted Rights" as defined in Clause
252.227-7013 (c) (1) of DFARs.  Notwithstanding the foregoing, the
authors grant the U.S. Government and others acting in its behalf
permission to use and distribute the software in accordance with the
terms specified in this license. 
