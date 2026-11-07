# Tembuku™ – Feeder Tap Designer · Pemberitahuan kepengarangan / Authorship notice

**Pencipta dan pemegang hak cipta / Author and copyright holder:** Joseph Edward Timothy Siahaan (2026).
Lisensi / Licence: GNU GPL v3 atau lebih baru, **dengan syarat tambahan pasal 7** (lihat [LICENSE](LICENSE)).

## Rilis resmi / Official releases
- QGIS Plugin Repository: *Tembuku - Feeder Tap Designer* (plugins.qgis.org), diunggah oleh pembuat.
- Kode sumber: https://github.com/jetstimo/tembuku
- Setiap rilis resmi memuat `RILIS.json` yang **ditandatangani secara digital** (Ed25519) dengan kunci privat
  pembuat. Plugin memeriksa tanda tangan itu sendiri; hasilnya tercetak di kepala setiap laporan
  dan di dialog *Tentang Tembuku*.

- **Sidik kunci rilis resmi / official release key fingerprint: `92C4-D078-D1FC-1C5B`.** Rilis yang tampil dengan sidik kunci lain
  BUKAN rilis resmi Tembuku, apa pun nama pembuat yang tertulis. Sidik yang sama diterbitkan di halaman plugin
  plugins.qgis.org (deskripsi *About*) dan di https://github.com/jetstimo/tembuku.

| Status di laporan | Arti |
|---|---|
| ASLI – rilis resmi … ditandatangani … (kunci 92C4-D078-D1FC-1C5B) | Paket resmi, tidak ada berkas yang diubah |
| DIMODIFIKASI dari rilis resmi … | Ada berkas yang diubah/ditambah setelah rilis – bukan rilis resmi |
| TIDAK RESMI … kunci resmi 92C4-D078-D1FC-1C5B | Tanda tangan dibuat ulang atau kunci diganti – bukan kunci pembuat |
| salinan pengembangan | Tidak ada tanda tangan rilis |

## Memeriksa keaslian / Verifying a copy
1. **About** di QGIS: status dan sidik kunci harus `ASLI … (kunci 92C4-D078-D1FC-1C5B)`.
2. **Verify online** di About: mencocokkan isi salinan dengan daftar rilis resmi `RILIS_RESMI.json` di GitHub pembuat.
3. Pemeriksa independen pembuat: `python rilis_resmi.py cek tembuku.<versi>.zip` (membawa kunci resmi sendiri dan tidak
   menjalankan kode dari paket yang diperiksa). Hasil: ASLI / DIMODIFIKASI / PALSU (kunci diganti) / TIDAK RESMI.

## Memodifikasi / Modifying
Boleh, sesuai GPL v3. Syaratnya (LICENSE, pasal 7): pertahankan nama dan hak cipta pembuat (di kode, metadata, dialog
About dan kepala laporan), beri nama dan logo lain, tandai sebagai modifikasi ("Berbasis Tembuku oleh Joseph Edward
Timothy Siahaan, dimodifikasi oleh …, tanggal …"), dan jangan mengaku sebagai pembuat atau pemilik Tembuku.

## Bukti kepengarangan / Evidence of authorship
Riwayat commit di repositori GitHub, unggahan pertama di QGIS Plugin Repository atas nama pembuat, kunci tanda tangan
rilis, dan arsip rilis bertanggal (`tembuku.<versi>.zip` + SHA-256) disimpan oleh pembuat.
