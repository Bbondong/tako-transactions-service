"""Règles communes aux courses : coordonnées, état partagé et historique."""
import math
from datetime import datetime

from flask import g, jsonify

from src.data import fetch_all, fetch_one

# Statuts encore suivis (positions acceptées, course visible comme « en cours »).
ACTIVE_STATUSES = ('pending', 'assigned', 'arrived', 'in_transit')


def coordinates(data):
    """(latitude, longitude) valides, sinon None. Les apps envoient des noms explicites."""
    try:
        latitude = float(data['latitude'])
        longitude = float(data['longitude'])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(latitude) and math.isfinite(longitude) and
            -90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude


def distance_km(lat1, lon1, lat2, lon2):
    a1, a2 = math.radians(float(lat1)), math.radians(float(lat2))
    d_lat = a2 - a1
    d_lon = math.radians(float(lon2) - float(lon1))
    h = math.sin(d_lat / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(d_lon / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


def record(cursor, course_id, status, actor, user_id, point=None):
    """Ajoute une étape à l'historique, dans la transaction du changement.

    L'historique n'est jamais modifié : il garde qui a fait quoi, quand et où.
    """
    latitude, longitude = point if point else (None, None)
    cursor.execute('INSERT INTO course_status_history '
                   '(course_id, status, actor, user_id, latitude, longitude) '
                   'VALUES (%s,%s,%s,%s,%s,%s)',
                   (course_id, status, actor, user_id, latitude, longitude))


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _optional_float(value):
    return float(value) if value is not None else None


def positions(course_id):
    rows = fetch_all('SELECT actor, latitude, longitude, updated_at FROM course_positions '
                     'WHERE course_id=%s', (course_id,))
    return {row['actor']: {'latitude': float(row['latitude']),
                           'longitude': float(row['longitude']),
                           'updated_at': _iso(row['updated_at'])} for row in rows}


def timeline(course_id):
    rows = fetch_all('SELECT status, actor, created_at FROM course_status_history '
                     'WHERE course_id=%s ORDER BY created_at, id', (course_id,))
    return [{'status': row['status'], 'actor': row['actor'], 'at': _iso(row['created_at'])}
            for row in rows]


COURSE_COLUMNS = ('id, user_id, driver_user_id, status, driver_name, vehicle, price, pickup, dropoff, '
                  'pickup_latitude, pickup_longitude, destination_latitude, destination_longitude, '
                  'cargo_type, weight, description, is_fragile, is_express, created_at')


def course_for(course_id, role):
    """La course si le compte connecté en est le client ou le chauffeur."""
    field = 'user_id' if role == 'client' else 'driver_user_id'
    return fetch_one(f'SELECT {COURSE_COLUMNS} FROM courses WHERE id=%s AND {field}=%s',
                     (course_id, g.user_id))


def snapshot(course):
    """État partagé par les deux apps : course, positions réelles et chronologie."""
    return jsonify(course={'id': course['id'], 'status': course['status'],
                           'driver_name': course['driver_name'], 'vehicle': course['vehicle'],
                           'price': _optional_float(course['price']),
                           'pickup': course['pickup'], 'dropoff': course['dropoff'],
                           'pickup_latitude': float(course['pickup_latitude']),
                           'pickup_longitude': float(course['pickup_longitude']),
                           'destination_latitude': float(course['destination_latitude']),
                           'destination_longitude': float(course['destination_longitude']),
                           'cargo_type': course.get('cargo_type'),
                           'weight': _optional_float(course.get('weight')),
                           'description': course.get('description'),
                           'is_fragile': bool(course.get('is_fragile')),
                           'is_express': bool(course.get('is_express')),
                           'created_at': _iso(course.get('created_at'))},
                   positions=positions(course['id']),
                   timeline=timeline(course['id']))


def update_position(cursor, course_id, role, point):
    """Dernière position d'un participant (une ligne par acteur et par course)."""
    cursor.execute('INSERT INTO course_positions '
                   '(course_id, actor, user_id, latitude, longitude) VALUES (%s,%s,%s,%s,%s) '
                   'ON DUPLICATE KEY UPDATE user_id=VALUES(user_id), latitude=VALUES(latitude), '
                   'longitude=VALUES(longitude), updated_at=CURRENT_TIMESTAMP(3)',
                   (course_id, role, g.user_id, *point))
    if role == 'driver':
        # Garde les anciens lecteurs (courses.driver_latitude) synchronisés.
        cursor.execute('UPDATE courses SET driver_latitude=%s, driver_longitude=%s WHERE id=%s',
                       (*point, course_id))
