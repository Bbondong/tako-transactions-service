"""Courses côté client : création, historique, annulation et suivi partagé."""
import base64
import math

from flask import Blueprint, g, jsonify, request

from src.auth import client_authenticated
from src.courses import (ACTIVE_STATUSES, coordinates, course_for, record, snapshot,
                         update_position)
from src.data import Database, fetch_all, fetch_one

client_courses_bp = Blueprint('client_courses', __name__, url_prefix='/api/v1')


def _upload_photo(photo):
    """URL Cloudinary de la photo (JPEG/PNG, 5 Mo max), ou un message d'erreur."""
    if not isinstance(photo, str) or len(photo) > 7_000_000:
        return None, 'Photo trop volumineuse.'
    try:
        raw = base64.b64decode(photo, validate=True)
    except ValueError:
        return None, 'Photo invalide (JPEG ou PNG, 5 Mo max).'
    if len(raw) > 5_000_000 or not (raw.startswith(b'\xff\xd8\xff') or raw.startswith(b'\x89PNG\r\n\x1a\n')):
        return None, 'Photo invalide (JPEG ou PNG, 5 Mo max).'
    mime = 'image/jpeg' if raw.startswith(b'\xff') else 'image/png'
    try:
        import cloudinary.uploader
        return cloudinary.uploader.upload('data:%s;base64,%s' % (mime, photo),
                                          folder='tako/cargo', resource_type='image')['secure_url'], None
    except Exception:
        return None, 'Téléversement de la photo impossible.'


@client_courses_bp.post('/courses')
@client_authenticated
def create_course():
    data = request.get_json(silent=True) or {}
    pickup, dropoff = str(data.get('pickup', '')).strip(), str(data.get('dropoff', '')).strip()
    cargo_type = str(data.get('cargo_type', '')).strip()
    try:
        lat1, lon1 = float(data['pickup_latitude']), float(data['pickup_longitude'])
        lat2, lon2 = float(data['destination_latitude']), float(data['destination_longitude'])
        weight = float(data['weight'])
    except (KeyError, ValueError, TypeError):
        return jsonify(message='Coordonnées ou poids invalides.'), 400
    if (not pickup or not dropoff or not cargo_type or len(pickup) > 500 or len(dropoff) > 500
            or len(cargo_type) > 100 or not all(map(math.isfinite, [lat1, lon1, lat2, lon2, weight]))
            or weight <= 0 or not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90
                                   and -180 <= lon1 <= 180 and -180 <= lon2 <= 180)):
        return jsonify(message='Informations de course invalides.'), 400
    dimensions = []
    for key in ('length', 'width', 'height'):
        try:
            number = float(data[key]) if data.get(key) is not None else None
            if number is not None and (not math.isfinite(number) or number <= 0):
                raise ValueError()
        except (ValueError, TypeError):
            return jsonify(message='Dimensions invalides.'), 400
        dimensions.append(number)
    description = str(data.get('description') or '').strip()[:2000]
    vehicle = str(data.get('vehicle') or '').strip()[:200] or None
    # Prix calculé par l'app client et enregistré tel quel.
    price = data.get('price')
    try:
        price = float(price) if price is not None else None
        if price is not None and (not math.isfinite(price) or price <= 0 or price > 100_000_000):
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify(message='Prix invalide.'), 400
    photo_url = None
    if data.get('photo_base64'):
        photo_url, error = _upload_photo(data['photo_base64'])
        if error:
            return jsonify(message=error), 503 if 'Téléversement' in error else 400

    with Database() as cursor:
        cursor.execute('INSERT INTO courses (user_id,pickup,dropoff,pickup_latitude,pickup_longitude,'
                       'destination_latitude,destination_longitude,cargo_type,weight,description,'
                       'length_cm,width_cm,height_cm,is_fragile,is_express,photo_url,vehicle,price,status) '
                       "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')",
                       (g.user_id, pickup, dropoff, lat1, lon1, lat2, lon2, cargo_type, weight,
                        description, *dimensions, bool(data.get('is_fragile')),
                        bool(data.get('is_express')), photo_url, vehicle, price))
        course_id = cursor.lastrowid
        cursor.execute('INSERT INTO course_positions '
                       '(course_id, actor, user_id, latitude, longitude) '
                       "VALUES (%s,'client',%s,%s,%s)", (course_id, g.user_id, lat1, lon1))
        record(cursor, course_id, 'pending', 'client', g.user_id, (lat1, lon1))
    return jsonify(id=course_id, status='pending'), 201


@client_courses_bp.get('/courses')
@client_authenticated
def list_courses():
    # Historique complet du client, avec les coordonnées pour la carte.
    return jsonify(courses=fetch_all(
        'SELECT id, pickup, dropoff, price, status, driver_name, vehicle, '
        'pickup_latitude, pickup_longitude, destination_latitude, destination_longitude, '
        'cargo_type, weight, description, is_fragile, is_express, created_at '
        'FROM courses WHERE user_id=%s ORDER BY created_at DESC', (g.user_id,)))


@client_courses_bp.get('/courses/<int:course_id>')
@client_courses_bp.get('/courses/<int:course_id>/positions')
@client_authenticated
def course_detail(course_id):
    course = course_for(course_id, 'client')
    if not course:
        return jsonify(message='Course introuvable.'), 404
    return snapshot(course)


@client_courses_bp.post('/courses/<int:course_id>/cancel')
@client_authenticated
def cancel_course(course_id):
    # UPDATE conditionnel : face à un chauffeur qui récupère le colis au même
    # moment, un seul des deux l'emporte, au niveau de la base.
    with Database() as cursor:
        changed = cursor.execute("UPDATE courses SET status='cancelled' WHERE id=%s AND user_id=%s "
                                 "AND status IN ('pending','assigned')", (course_id, g.user_id))
        if changed:
            record(cursor, course_id, 'cancelled', 'client', g.user_id)
    if not changed:
        if not fetch_one('SELECT id FROM courses WHERE id=%s AND user_id=%s', (course_id, g.user_id)):
            return jsonify(message='Course introuvable.'), 404
        return jsonify(message='Cette course ne peut plus être annulée.'), 409
    return jsonify(id=course_id, status='cancelled')


@client_courses_bp.put('/courses/<int:course_id>/position')
@client_authenticated
def client_position(course_id):
    point = coordinates(request.get_json(silent=True) or {})
    if point is None:
        return jsonify(message='Coordonnées invalides.'), 400
    with Database() as cursor:
        # Verrou : un changement de statut concurrent ne peut pas autoriser une mise à jour tardive.
        cursor.execute('SELECT id, user_id, status FROM courses WHERE id=%s FOR UPDATE', (course_id,))
        course = cursor.fetchone()
        if not course:
            return jsonify(message='Course introuvable.'), 404
        if course['user_id'] != g.user_id:
            return jsonify(message='Accès interdit à cette course.'), 403
        if course['status'] not in ACTIVE_STATUSES:
            return jsonify(message='Le suivi de cette course est terminé.'), 409
        update_position(cursor, course_id, 'client', point)
    return snapshot(course_for(course_id, 'client'))
