import os
import re
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
import psycopg2

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'kunci-rahasia-default')

# Membaca URL Database (otomatis pakai SQLite jika dijalankan di laptop)
database_url = os.environ.get('DATABASE_URL', 'sqlite:///catatan.db')

# Perbaikan string untuk PostgreSQL (Wajib untuk Railway)
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True}

db = SQLAlchemy(app)

# Menghapus async_mode='eventlet' agar terhindar dari Error 502 / Deprecation Warning
socketio = SocketIO(app, cors_allowed_origins="*")


class Kategori(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    ikon = db.Column(db.String(10), default='📁')
    urutan = db.Column(db.Integer, default=0)


class Catatan(db.Model):
    id = db.Column(db.String(50), db.ForeignKey('kategori.id'), primary_key=True)
    konten = db.Column(db.Text, nullable=True)


KATEGORI_DEFAULT = [
    {"id": "todo", "nama": "TO DO", "ikon": "📌"},
    {"id": "makan", "nama": "MAKAN", "ikon": "🍔"},
    {"id": "main", "nama": "MAIN", "ikon": "🎮"},
    {"id": "alam", "nama": "ALAM", "ikon": "🍃"},
    {"id": "nonton", "nama": "NONTON", "ikon": "🎬"},
    {"id": "tempat_jalan", "nama": "TEMPAT JALAN", "ikon": "🗺️"},
    {"id": "daerah", "nama": "DAERAH", "ikon": "📍"},
    {"id": "foto", "nama": "FOTO", "ikon": "📸"},
]

with app.app_context():
    db.create_all()
    for urutan, kat in enumerate(KATEGORI_DEFAULT):
        if not db.session.get(Kategori, kat["id"]):
            db.session.add(Kategori(id=kat["id"], nama=kat["nama"], ikon=kat["ikon"], urutan=urutan))
        if not db.session.get(Catatan, kat["id"]):
            db.session.add(Catatan(id=kat["id"], konten=""))
    db.session.commit()


def buat_slug(nama):
    """Ubah nama kategori jadi id yang aman dipakai (huruf kecil, underscore)."""
    slug = nama.strip().lower()
    slug = re.sub(r'[^a-z0-9]+', '_', slug)
    slug = slug.strip('_')
    return slug or 'kategori'


@app.route('/')
def index():
    semua_kategori = Kategori.query.order_by(Kategori.urutan).all()
    semua_catatan = Catatan.query.all()
    notes_data = {c.id: (c.konten or "") for c in semua_catatan}
    kategori_list = [{"id": k.id, "nama": k.nama, "ikon": k.ikon} for k in semua_kategori]
    return render_template('index.html', notes=notes_data, kategori_list=kategori_list)


@socketio.on('edit_kategori')
def handle_edit(data):
    kategori = data['kategori']
    konten = data['konten']

    # Perbaikan: Menggunakan session.get agar tidak muncul kuning (LegacyAPIWarning)
    catatan = db.session.get(Catatan, kategori)
    if catatan:
        catatan.konten = konten
        db.session.commit()

    emit('update_layar', data, broadcast=True, include_self=False)


@socketio.on('tambah_kategori')
def handle_tambah_kategori(data):
    nama = (data.get('nama') or '').strip()[:60]
    ikon = (data.get('ikon') or '📁').strip()[:8]
    if not nama:
        return

    slug_dasar = buat_slug(nama)
    slug = slug_dasar
    counter = 1
    while db.session.get(Kategori, slug):
        counter += 1
        slug = f"{slug_dasar}_{counter}"

    urutan_maks = db.session.query(db.func.max(Kategori.urutan)).scalar() or 0

    db.session.add(Kategori(id=slug, nama=nama, ikon=ikon, urutan=urutan_maks + 1))
    db.session.add(Catatan(id=slug, konten=""))
    db.session.commit()

    emit('kategori_ditambahkan', {"id": slug, "nama": nama, "ikon": ikon}, broadcast=True)


@socketio.on('hapus_kategori')
def handle_hapus_kategori(data):
    kat_id = data.get('id')
    if not kat_id:
        return

    kategori = db.session.get(Kategori, kat_id)
    catatan = db.session.get(Catatan, kat_id)
    if kategori:
        db.session.delete(kategori)
    if catatan:
        db.session.delete(catatan)
    db.session.commit()

    emit('kategori_dihapus', {"id": kat_id}, broadcast=True)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
