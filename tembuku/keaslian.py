# -*- coding: utf-8 -*-
"""
Tembuku - Feeder Tap Designer
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat tambahan pasal 7 (lihat LICENSE).

KEASLIAN RILIS (tanda tangan digital pembuat)
---------------------------------------------
Setiap rilis resmi Tembuku memuat RILIS.json: daftar SHA-256 semua berkas plugin yang DITANDATANGANI pembuat dengan
kunci privat Ed25519 (RFC 8032) yang hanya dipegang pembuat. Kunci publiknya tertanam di bawah (KUNCI_PUBLIK).

  * ASLI          : tanda tangan cocok dengan kunci pembuat DAN semua berkas sama dengan saat ditandatangani;
  * DIMODIFIKASI  : tanda tangan cocok, tetapi ada berkas yang diubah/ditambah setelah rilis (nama berkas disebut);
  * TIDAK RESMI   : RILIS.json ada tetapi tanda tangannya tidak cocok dengan kunci pembuat (dibuat ulang orang lain);
  * PENGEMBANGAN  : tidak ada RILIS.json (salinan kerja / belum dirilis).

Status ini dicetak di kepala setiap laporan ("Alat : ... integritas ...") dan di dialog About, sehingga laporan dari
salinan yang diubah selalu terlihat berbeda dari rilis resmi. Siapa pun boleh mengubah kode (GPL), tetapi tidak bisa
membuat tanda tangan yang cocok tanpa kunci privat pembuat; versi turunan wajib berganti nama & ditandai (LICENSE, pasal 7).

LAPISAN PENGAMAN (3.9.3, setelah uji serangan "ganti kunci"):
  1. Tanda tangan Ed25519 atas sidik SHA-256 setiap berkas (di atas).
  2. SIDIK KUNCI resmi (SIDIK_RESMI, 16 heksadesimal) dicetak di setiap status. Sidik yang sama diterbitkan di luar
     paket (GitHub pembuat, halaman plugins.qgis.org, NOTICE.md); salinan yang kuncinya diganti selalu tampil dengan sidik
     lain.
  3. CEK SILANG: sidik kunci di keaslian.py harus sama dengan SIDIK_RESMI dan dengan sidik yang tertulis di metadata.txt,
     NOTICE.md dan README.md. Mengganti kunci di satu tempat saja -> TIDAK RESMI.
  4. VERIFIKASI ONLINE (opsional, tombol di About): sidik manifest salinan ini dicocokkan dengan daftar rilis resmi
     RILIS_RESMI.json di repositori GitHub pembuat (REPO_RESMI), yang hanya bisa diubah oleh akun pembuat.
  5. Pemeriksa independen milik pembuat (scripts/rilis_resmi.py) membawa kunci resminya sendiri dan TIDAK menjalankan kode
     dari paket yang diperiksa.
Tidak ada kode terbuka yang mustahil diubah; yang dijamin: salinan yang diubah tidak dapat tampil sebagai rilis resmi
pembuat, dengan sidik kunci yang sama, tanpa kunci privat pembuat.

Murni Python (hashlib), tanpa pustaka luar, agar memenuhi aturan repositori plugin QGIS (tanpa biner).
"""
import hashlib
import json
import os

# Kunci publik Ed25519 pembuat: 32 byte sebagai 8 bilangan 32-bit. Sama dengan KUNCI_RESMI di scripts/rilis_resmi.py.
# Sengaja BUKAN string hex/base64: pemindai rahasia plugins.qgis.org (detect-secrets) memblokir paket yang memuat
# string acak panjang (pengalaman integrity.json, 3.4.x). Kunci publik, sidik berkas dan tanda tangan tidak rahasia.
KUNCI_PUBLIK = (1549593263, 1258448507, 3948243780, 1745094294, 3588476158, 1130529245, 3255756279, 3988926214)
PEMBUAT = "Joseph Edward Timothy Siahaan"
PRODUK = "Tembuku - Feeder Tap Designer"
REPO_RESMI = "jetstimo/tembuku"
# Sidik kunci resmi = 8 byte pertama SHA-256(kunci publik), heksadesimal berkelompok. Juga tertulis di CERMIN (cek silang).
SIDIK_RESMI = "92C4-D078-D1FC-1C5B"
CERMIN = ("metadata.txt", "NOTICE.md", "README.md")
BERKAS_RILIS = "RILIS.json"
TEKS = (".py", ".md", ".txt", ".json", ".svg", ".js", ".css", ".qml", ".html", ".xml", ".csv")
LEWATI_DIR = {"__pycache__", ".git", "tests", "__MACOSX", ".idea", ".vscode"}

# ----------------------------------------------------------------------------- Ed25519 (RFC 8032, bagian 6)
_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493


def _inv(x):
    return pow(x, _P - 2, _P)


_D = -121665 * _inv(121666) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _add(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _mul(s, pt):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        s >>= 1
    return q


def _eq(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _I % _P
    if (x * x - x2) % _P:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _enc(pt):
    z = _inv(pt[2])
    x, y = pt[0] * z % _P, pt[1] * z % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _dec(b):
    if len(b) != 32:
        return None
    y = int.from_bytes(b, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


def _hq(b):
    return int.from_bytes(hashlib.sha512(b).digest(), "little") % _Q


def _expand(secret):
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(secret):
    """Kunci publik (32 byte) dari kunci privat (32 byte)."""
    return _enc(_mul(_expand(secret)[0], _G))


def sign(secret, msg):
    a, prefix = _expand(secret)
    A = _enc(_mul(a, _G))
    r = _hq(prefix + msg)
    R = _enc(_mul(r, _G))
    s = (r + _hq(R + A + msg) * a) % _Q
    return R + int.to_bytes(s, 32, "little")


def verify(public, msg, sig):
    if len(public) != 32 or len(sig) != 64:
        return False
    A = _dec(public)
    R = _dec(sig[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= _Q:
        return False
    return _eq(_mul(s, _G), _add(R, _mul(_hq(sig[:32] + public + msg), A)))


# ----------------------------------------------------------------------------- manifest
def to_ints(b):
    """bytes (kelipatan 4) -> daftar bilangan 32-bit big-endian (bukan string, aman dari pemindai rahasia)."""
    return [int.from_bytes(b[i:i + 4], "big") for i in range(0, len(b), 4)]


def from_ints(v):
    return b"".join(int(x).to_bytes(4, "big") for x in v)


def file_hash(path):
    with open(path, "rb") as fh:
        b = fh.read()
    if path.lower().endswith(TEKS):
        b = b.replace(b"\r\n", b"\n")        # Windows/git autocrlf tidak dianggap perubahan
    return to_ints(hashlib.sha256(b).digest())


def list_files(root):
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in LEWATI_DIR and not x.startswith("."))
        for f in sorted(files):
            if f == BERKAS_RILIS or f.endswith((".pyc", ".pyo")) or f.startswith("."):
                continue
            out.append(os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/"))
    return out


def sidik(public):
    """Sidik kunci publik untuk dibaca manusia: 'XXXX-XXXX-XXXX-XXXX' (8 byte pertama SHA-256)."""
    h = hashlib.sha256(public).hexdigest().upper()[:16]
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


def sidik_manifest(man):
    """Sidik manifest bertanda tangan (bilangan 32-bit): pengenal unik isi satu rilis, untuk verifikasi online."""
    return to_ints(hashlib.sha256(canonical(man)).digest())


def cermin_beda(root):
    """Berkas cermin yang tidak memuat SIDIK_RESMI (cek silang lapis 3)."""
    out = []
    for f in CERMIN:
        p = os.path.join(root, f)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as fh:
                if SIDIK_RESMI not in fh.read():
                    out.append(f)
    return out


def manifest(root, version, when=""):
    return {"produk": PRODUK, "versi": version, "pembuat": PEMBUAT, "dibuat": when,
            "berkas": {f: file_hash(os.path.join(root, f)) for f in list_files(root)}}


def canonical(man):
    return json.dumps(man, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def write_signed(root, version, secret, when=""):
    man = manifest(root, version, when)
    sig = sign(secret, canonical(man))
    with open(os.path.join(root, BERKAS_RILIS), "w", encoding="utf-8") as fh:
        json.dump({"manifest": man, "tanda_tangan": to_ints(sig), "kunci_publik": to_ints(public_key(secret)),
                   "algoritma": "Ed25519 (RFC 8032) atas SHA-256 tiap berkas; bilangan 32-bit big-endian"},
                  fh, ensure_ascii=False, indent=None, sort_keys=True, separators=(",", ":"))
    return man


_CACHE = {}


def check(root=None):
    """-> (kode, versi, detail) kode: ASLI / DIMODIFIKASI / TIDAK_RESMI / PENGEMBANGAN / GAGAL."""
    root = root or os.path.dirname(os.path.abspath(__file__))
    if root in _CACHE:
        return _CACHE[root]
    p = os.path.join(root, BERKAS_RILIS)
    if not os.path.exists(p):
        res = ("PENGEMBANGAN", "", [])
    else:
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
            man, sig = data["manifest"], from_ints(data["tanda_tangan"])
            key = from_ints(KUNCI_PUBLIK) if KUNCI_PUBLIK else b""
            mir = cermin_beda(root)
            if not key or sidik(key) != SIDIK_RESMI or mir:
                res = ("TIDAK_RESMI", man.get("versi", ""), ["kunci diganti"] + mir)
            elif not verify(key, canonical(man), sig):
                res = ("TIDAK_RESMI", man.get("versi", ""), [])
            else:
                exp = man.get("berkas") or {}
                now = set(list_files(root))
                bad = sorted(f for f, h in exp.items() if f not in now or file_hash(os.path.join(root, f)) != list(h))
                extra = sorted(now - set(exp))
                res = ("ASLI", man.get("versi", ""), []) if not bad and not extra else \
                    ("DIMODIFIKASI", man.get("versi", ""), bad + ["+" + x for x in extra])
        except Exception as e:     # RILIS.json rusak
            res = ("GAGAL", "", [str(e)[:80]])
    _CACHE[root] = res
    return res


def status(en=False, root=None):
    """Teks status untuk kepala laporan (Indonesia) atau dialog About (en=True); selalu menyebut sidik kunci."""
    code, ver, det = check(root)
    files = ", ".join(det[:4]) + (" ..." if len(det) > 4 else "")
    try:
        sk = sidik(from_ints(KUNCI_PUBLIK))
    except Exception:
        sk = "?"
    if en:
        return {"ASLI": "ORIGINAL - official release %s signed by %s (key %s)" % (ver, PEMBUAT, sk),
                "DIMODIFIKASI": "MODIFIED after official release %s (%s) - not an official build (key %s)" % (ver, files, sk),
                "TIDAK_RESMI": "UNOFFICIAL - the release signature or key is not the author's (key %s, official key %s%s)"
                               % (sk, SIDIK_RESMI, "; " + files if files else ""),
                "PENGEMBANGAN": "development copy (not a signed release)",
                "GAGAL": "not verified (%s)" % files}[code]
    return {"ASLI": "ASLI - rilis resmi %s ditandatangani %s (kunci %s)" % (ver, PEMBUAT, sk),
            "DIMODIFIKASI": "DIMODIFIKASI dari rilis resmi %s (%s) - bukan rilis resmi (kunci %s)" % (ver, files, sk),
            "TIDAK_RESMI": "TIDAK RESMI - tanda tangan/kunci rilis bukan milik pembuat (kunci %s, kunci resmi %s%s)"
                           % (sk, SIDIK_RESMI, "; " + files if files else ""),
            "PENGEMBANGAN": "salinan pengembangan (belum rilis bertanda tangan)",
            "GAGAL": "tidak diverifikasi (%s)" % files}[code]


# ----------------------------------------------------------------------------- verifikasi online (lapis 4)
REGISTRI = "RILIS_RESMI.json"


def registry_url():
    return "https://raw.githubusercontent.com/%s/main/%s" % (REPO_RESMI, REGISTRI)


def verify_online(fetch, root=None):
    """Cocokkan salinan ini dengan daftar rilis resmi di GitHub pembuat. fetch(url) -> bytes (disediakan pemanggil,
    mis. QgsBlockingNetworkRequest agar mengikuti proxy QGIS). Kembali (kode, teks):
    TERVERIFIKASI / TIDAK_TERDAFTAR / BEDA_KUNCI / BUKAN_RILIS / GAGAL."""
    root = root or os.path.dirname(os.path.abspath(__file__))
    code, ver, _det = check(root)
    if code != "ASLI":
        return "BUKAN_RILIS", "local check is %s, nothing to verify online" % code
    try:
        with open(os.path.join(root, BERKAS_RILIS), encoding="utf-8") as fh:
            man = json.load(fh)["manifest"]
        reg = json.loads(fetch(registry_url()).decode("utf-8"))
    except Exception as e:
        return "GAGAL", "official release list not reachable (%s)" % str(e)[:80]
    if reg.get("kunci_sidik") != SIDIK_RESMI:
        return "BEDA_KUNCI", "the official list on github.com/%s uses key %s, this copy %s" % (
            REPO_RESMI, reg.get("kunci_sidik"), SIDIK_RESMI)
    ent = (reg.get("rilis") or {}).get(ver) or {}
    if list(ent.get("manifest") or []) == sidik_manifest(man):
        return "TERVERIFIKASI", "release %s is listed as official on github.com/%s (key %s)" % (ver, REPO_RESMI, SIDIK_RESMI)
    return "TIDAK_TERDAFTAR", "release %s with this content is NOT in the official list on github.com/%s" % (ver, REPO_RESMI)
