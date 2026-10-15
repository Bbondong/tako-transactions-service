"""Courses côté chauffeur : présence, offres proches, acceptation, GPS et statuts."""
import math
from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request

from src.auth import driver_authenticated
from src.courses import (coordinates, course_for, distance_km, record, snapshot,
                         update_position)
from src.data import Database, fetch_all, fetch_one

driver_courses_bp = Blueprint('driver_courses', __name__, url_prefix='/api/v1/driver')

# Offres visibles dans ce rayon, par des chauffeurs signalés depuis moins de PRESENCE_TTL.
OFFER_RADIUS_KM = 15
PRESENCE_TTL = timedelta(seconds=30)

# Ordre imposé des étapes : chaque statut n'est accepté qu'après le précédent.
PREDECESSORS = {'arrived': 'assigned', 'in_transit': 'arrived', 'delivered': 'in_transit'}


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fresh(presence):
    return bool(presence and presence['available'] and presence['updated_at'] >= _now() - PRESENCE_TTL)


@driver_courses_bp.put('/presence')
@driver_authenticated
def update_presence():
    data = request.get_json(silent=True) or {}
    point = coordinates(data)
    if point is None or not isinstance(data.get('available'), bool):
        return jsonify(message='Position et disponibilité requises.'), 400
    with Database() as cursor:
        cursor.execute('SELECT driver_user_id FROM driver_presence '
                       'WHERE driver_user_id=%s FOR UPDATE', (g.user_id,))
        cursor.execute("SELECT id FROM courses WHERE driver_user_id=%s "
                       "AND status IN ('assigned','arrived','in_transit') LIMIT 1", (g.user_id,))
        # Un chauffeur déjà en course ne reçoit pas d'autre offre.
        available = data['available'] and cursor.fetchone() is None
        cursor.execute(
            'INSERT INTO driver_presence (driver_user_id, latitude, longitude, available) '
            'VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE '
            'latitude=VALUES(latitude), longitude=VALUES(longitude), '
            'available=VALUES(available), updated_at=CURRENT_TIMESTAMP(3)',
            (g.user_id, *point, available))
    return jsonify(available=available)


@driver_courses_bp.get('/courses/available')
@driver_authenticated
def available_courses():
    presence = fetch_one('SELECT latitude, longitude, available, updated_at FROM driver_presence '
                         'WHERE driver_user_id=%s', (g.user_id,))
    if not _fresh(presence):
        return jsonify(courses=[])
    latitude, longitude = float(presence['latitude']), float(presence['longitude'])
    # Fenêtre SQL bornée, puis tri par vraie distance.
    lon_span = 0.15 / max(0.2, math.cos(math.radians(latitude)))
    rows = fetch_all(
        'SELECT id, pickup, dropoff, pickup_latitude, pickup_longitude, '
        'destination_latitude, destination_longitude, cargo_type, weight, '
        'description, is_fragile, is_express, length_cm, width_cm, height_cm, '
        'vehicle, price, created_at FROM courses '
        "WHERE status='pending' AND driver_user_id IS NULL "
        'AND pickup_latitude BETWEEN %s AND %s '
        'AND pickup_longitude BETWEEN %s AND %s '
        'ORDER BY created_at DESC LIMIT 200',
        (latitude - 0.15, latitude + 0.15, longitude - lon_span, longitude + lon_span))
    for row in rows:
        row['distance_km'] = round(distance_km(
            latitude, longitude, row['pickup_latitude'], row['pickup_longitude']), 1)
    return jsonify(courses=sorted((row for row in rows if row['distance_km'] <= OFFER_RADIUS_KM),
                                  key=lambda row: row['distance_km']))


@driver_courses_bp.get('/courses/active')
@driver_authenticated
def active_course():
    row = fetch_one("SELECT id FROM courses WHERE driver_user_id=%s "
                    "AND status IN ('assigned','arrived','in_transit') "
                    'ORDER BY id DESC LIMIT 1', (g.user_id,))
    if not row:
        return jsonify(course=None)
    return snapshot(course_for(row['id'], 'driver'))


@driver_courses_bp.get('/courses/history')
@driver_authenticated
def history():
    """Courses passées et en cours du chauffeur, les plus récentes d'abord."""
    return jsonify(courses=fetch_all(
        'SELECT id, pickup, dropoff, price, status, vehicle, cargo_type, weight, created_at '
        'FROM courses WHERE driver_user_id=%s ORDER BY created_at DESC LIMIT 200', (g.user_id,)))


@driver_courses_bp.post('/courses/<int:course_id>/accept')
@driver_authenticated
def accept_course(course_id):
    point = coordinates(request.get_json(silent=True) or {})
    if point is None:
        return jsonify(message='Position du chauffeur invalide.'), 400
    offer = fetch_one("SELECT pickup_latitude, pickup_longitude FROM courses "
                      "WHERE id=%s AND status='pending' AND driver_user_id IS NULL", (course_id,))
    if not offer:
        return jsonify(message='Course indisponible.'), 409
    if distance_km(*point, offer['pickup_latitude'], offer['pickup_longitude']) > OFFER_RADIUS_KM:
        return jsonify(message=f'Course hors de votre zone de {OFFER_RADIUS_KM} km.'), 409
    info = fetch_one('SELECT nom, prenom FROM user_info WHERE id_user=%s', (g.user_id,))
    driver_name = (' '.join(str(info.get(key) or '').strip() for key in ('prenom', 'nom')).strip()
                   if info else None) or None
    with Database() as cursor:
        cursor.execute('SELECT available, updated_at FROM driver_presence '
                       'WHERE driver_user_id=%s FOR UPDATE', (g.user_id,))
        if not _fresh(cursor.fetchone()):
            return jsonify(message='Passez en ligne et activez votre position GPS.'), 409
        # UPDATE conditionnel : entre deux chauffeurs, la base désigne le gagnant.
        changed = cursor.execute("UPDATE courses SET driver_user_id=%s, driver_name=%s, status='assigned' "
                                 "WHERE id=%s AND status='pending' AND driver_user_id IS NULL",
                                 (g.user_id, driver_name, course_id))
        if changed:
            cursor.execute('UPDATE driver_presence SET available=0 WHERE driver_user_id=%s', (g.user_id,))
            update_position(cursor, course_id, 'driver', point)
            record(cursor, course_id, 'assigned', 'driver', g.user_id, point)
    if not changed:
        exists = fetch_one('SELECT id FROM courses WHERE id=%s', (course_id,))
        if not exists:
            return jsonify(message='Course introuvable.'), 404
        return jsonify(message='Course déjà attribuée.'), 409
    return snapshot(course_for(course_id, 'driver'))


@driver_courses_bp.get('/courses/<int:course_id>/positions')
@driver_authenticated
def course_positions(course_id):
    course = course_for(course_id, 'driver')
    if not course:
        return jsonify(message='Course introuvable ou accès interdit.'), 404
    return snapshot(course)


@driver_courses_bp.put('/courses/<int:course_id>/position')
@driver_authenticated
def driver_position(course_id):
    point = coordinates(request.get_json(silent=True) or {})
    if point is None:
        return jsonify(message='Coordonnées invalides.'), 400
    with Database() as cursor:
        cursor.execute('SELECT id, driver_user_id, status FROM courses WHERE id=%s FOR UPDATE', (course_id,))
        course = cursor.fetchone()
        if not course:
            return jsonify(message='Course introuvable.'), 404
        if course['driver_user_id'] != g.user_id:
            return jsonify(message='Accès interdit à cette course.'), 403
        if course['status'] not in ('assigned', 'arrived', 'in_transit'):
            return jsonify(message='Le suivi de cette course est terminé.'), 409
        update_position(cursor, course_id, 'driver', point)
    return snapshot(course_for(course_id, 'driver'))


@driver_courses_bp.put('/courses/<int:course_id>/status')
@driver_authenticated
def change_status(course_id):
    requested = str((request.get_json(silent=True) or {}).get('status') or '')
    previous = PREDECESSORS.get(requested)
    if not previous:
        return jsonify(message='Transition de course invalide.'), 400
    with Database() as cursor:
        changed = cursor.execute('UPDATE courses SET status=%s WHERE id=%s AND driver_user_id=%s AND status=%s',
                                 (requested, course_id, g.user_id, previous))
        if changed:
            # L'étape est datée et située à la dernière position connue du chauffeur.
            cursor.execute("SELECT latitude, longitude FROM course_positions "
                           "WHERE course_id=%s AND actor='driver'", (course_id,))
            last = cursor.fetchone()
            point = (float(last['latitude']), float(last['longitude'])) if last else None
            record(cursor, course_id, requested, 'driver', g.user_id, point)
    if not changed:
        return jsonify(message='Course absente ou statut déjà modifié.'), 409
    return snapshot(course_for(course_id, 'driver'))
