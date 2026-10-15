"""Parcours complets client ↔ chauffeur sur une base MySQL simulée en mémoire.

Les requêtes HTTP passent par la vraie application Flask (sécurité, jetons
JWT signés, routes) ; seule la base est remplacée.
"""
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.update(TAKO_JWT_SECRET='s' * 40, TAKO_CLIENT_ROLE_ID='3',
                  TAKO_DRIVER_ROLE_ID='2', TAKO_API_KEY='cle-interne-test')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402

import app as service  # noqa: E402
from src import auth, courses  # noqa: E402
from src.routes import client_courses, driver_courses  # noqa: E402

CLIENT, DRIVER, OTHER_DRIVER, OTHER_CLIENT = 10, 20, 21, 11
PICKUP = (-4.3217, 15.3125)
DROPOFF = (-4.3000, 15.3300)
NEAR = (-4.3300, 15.3000)  # chauffeur à ~2 km de la collecte


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FakeDb:
    """Sous-ensemble de MySQL utilisé par le service, avec ses verrous logiques."""

    def __init__(self):
        self.users = {CLIENT: 3, OTHER_CLIENT: 3, DRIVER: 2, OTHER_DRIVER: 2}
        self.courses, self.positions, self.presence, self.history = {}, {}, {}, []
        self.next_id = 1

    # --- fetch_one / fetch_all ------------------------------------
    def one(self, sql, params):
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def all(self, sql, params):
        sql = ' '.join(sql.split())
        if sql.startswith('SELECT id_user FROM user'):
            uid, role = params
            return [{'id_user': uid}] if self.users.get(uid) == role else []
        if sql.startswith('SELECT nom, prenom FROM user_info'):
            return [{'prenom': 'Jean', 'nom': 'Mukendi'}]
        if 'FROM driver_presence' in sql:
            p = self.presence.get(params[0])
            return [dict(p)] if p else []
        if 'FROM course_positions' in sql:
            return [dict(actor=a, **v) for (cid, a), v in self.positions.items() if cid == params[0]]
        if 'FROM course_status_history' in sql:
            return [h for h in self.history if h['course_id'] == params[0]]
        if 'FROM courses' in sql:
            return self._select_courses(sql, params)
        raise AssertionError(f'SQL inattendu : {sql}')

    def _select_courses(self, sql, params):
        rows = list(self.courses.values())
        if "status='pending' AND driver_user_id IS NULL AND pickup_latitude" in sql:
            return [dict(c) for c in rows if c['status'] == 'pending' and c['driver_user_id'] is None]
        if "status='pending' AND driver_user_id IS NULL" in sql:
            c = self.courses.get(params[0])
            return [dict(c)] if c and c['status'] == 'pending' and c['driver_user_id'] is None else []
        if 'WHERE driver_user_id=%s AND status IN' in sql:
            return [dict(c) for c in rows if c['driver_user_id'] == params[0]
                    and c['status'] in ('assigned', 'arrived', 'in_transit')]
        if 'WHERE driver_user_id=%s ORDER BY' in sql:
            return [dict(c) for c in rows if c['driver_user_id'] == params[0]]
        if 'WHERE user_id=%s ORDER BY' in sql:
            return [dict(c) for c in rows if c['user_id'] == params[0]]
        m = re.search(r'WHERE id=%s AND (user_id|driver_user_id)=%s', sql)
        if m:
            c = self.courses.get(params[0])
            return [dict(c)] if c and c[m.group(1)] == params[1] else []
        if 'WHERE id=%s' in sql:
            c = self.courses.get(params[0])
            return [dict(c)] if c else []
        raise AssertionError(f'SQL inattendu : {sql}')

    # --- curseur transactionnel ------------------------------------
    def execute(self, cursor, sql, params):
        sql = ' '.join(sql.split())
        if sql.startswith('INSERT INTO courses'):
            (uid, pickup, dropoff, lat1, lon1, lat2, lon2, cargo, weight, desc,
             length, width, height, fragile, express, photo, vehicle, price) = params
            cid = self.next_id
            self.next_id += 1
            self.courses[cid] = dict(
                id=cid, user_id=uid, driver_user_id=None, status='pending', driver_name=None,
                vehicle=vehicle, price=price, pickup=pickup, dropoff=dropoff,
                pickup_latitude=lat1, pickup_longitude=lon1, destination_latitude=lat2,
                destination_longitude=lon2, cargo_type=cargo, weight=weight, description=desc,
                is_fragile=fragile, is_express=express, length_cm=length, width_cm=width,
                height_cm=height, created_at=now())
            cursor.lastrowid = cid
            return 1
        if sql.startswith('INSERT INTO course_positions'):
            if len(params) == 4:  # position de départ du client
                cid, uid, lat, lon = params
                actor = 'client'
            else:
                cid, actor, uid, lat, lon = params
            self.positions[(cid, actor)] = dict(latitude=lat, longitude=lon, updated_at=now())
            return 1
        if sql.startswith('INSERT INTO course_status_history'):
            cid, status, actor, uid, lat, lon = params
            self.history.append(dict(course_id=cid, status=status, actor=actor, user_id=uid,
                                     latitude=lat, longitude=lon, created_at=now()))
            return 1
        if sql.startswith('INSERT INTO driver_presence'):
            uid, lat, lon, available = params
            self.presence[uid] = dict(latitude=lat, longitude=lon, available=int(available),
                                      updated_at=now())
            return 1
        if sql.startswith('UPDATE driver_presence SET available=0'):
            self.presence[params[0]]['available'] = 0
            return 1
        if sql.startswith("UPDATE courses SET status='cancelled'"):
            cid, uid = params
            c = self.courses.get(cid)
            if c and c['user_id'] == uid and c['status'] in ('pending', 'assigned'):
                c['status'] = 'cancelled'
                return 1
            return 0
        if sql.startswith('UPDATE courses SET driver_user_id='):
            uid, name, cid = params
            c = self.courses.get(cid)
            if c and c['status'] == 'pending' and c['driver_user_id'] is None:
                c.update(driver_user_id=uid, driver_name=name, status='assigned')
                return 1
            return 0
        if sql.startswith('UPDATE courses SET driver_latitude='):
            return 1
        if sql.startswith('UPDATE courses SET status=%s'):
            status, cid, uid, previous = params
            c = self.courses.get(cid)
            if c and c['driver_user_id'] == uid and c['status'] == previous:
                c['status'] = status
                return 1
            return 0
        if sql.startswith('SELECT latitude, longitude FROM course_positions'):
            p = self.positions.get((params[0], 'driver'))
            cursor.result = dict(p) if p else None
            return 1
        if sql.startswith('SELECT') and 'FROM courses WHERE id=%s FOR UPDATE' in sql:
            c = self.courses.get(params[0])
            cursor.result = dict(c) if c else None
            return 1
        if sql.startswith('SELECT') and ('FROM driver_presence' in sql or 'FROM courses' in sql):
            cursor.result = self.one(sql, params)
            return 1
        raise AssertionError(f'SQL inattendu : {sql}')


class Cursor:
    def __init__(self, db):
        self.db, self.result, self.lastrowid = db, None, None

    def execute(self, sql, params=()):
        return self.db.execute(self, sql, params)

    def fetchone(self):
        return self.result


def token(user_id, role, expired=False):
    issued = datetime.now(timezone.utc)
    exp = issued - timedelta(minutes=1) if expired else issued + timedelta(hours=1)
    return jwt.encode({'sub': str(user_id), 'role': role, 'iat': issued, 'exp': exp},
                      's' * 40, algorithm='HS256')


class TransactionsTest(unittest.TestCase):
    def setUp(self):
        self.db = db = FakeDb()

        class Database:
            def __enter__(_):
                return Cursor(db)

            def __exit__(_, *exc):
                return False

        for module in (auth, courses, client_courses, driver_courses):
            for name, value in (('fetch_one', db.one), ('fetch_all', db.all), ('Database', Database)):
                if hasattr(module, name):
                    setattr(module, name, value)
        self.http = service.app.test_client()

    def call(self, method, path, user=None, role=None, body=None, **kw):
        headers = {'X-Internal-Key': 'cle-interne-test'}
        if user:
            headers['Authorization'] = f'Bearer {token(user, role, **kw)}'
        response = self.http.open(path, method=method, json=body, headers=headers)
        return response.status_code, response.get_json()

    def client(self, method, path, body=None, user=CLIENT):
        return self.call(method, path, user, 'client', body)

    def driver(self, method, path, body=None, user=DRIVER):
        return self.call(method, path, user, 'driver', body)

    def create_course(self):
        status, data = self.client('POST', '/api/v1/courses', {
            'pickup': 'Ma position, Gombe', 'dropoff': 'Marché Central',
            'pickup_latitude': PICKUP[0], 'pickup_longitude': PICKUP[1],
            'destination_latitude': DROPOFF[0], 'destination_longitude': DROPOFF[1],
            'cargo_type': 'Boissons', 'weight': 120, 'description': '20 cartons',
            'is_fragile': True, 'vehicle': 'bus', 'price': 12500})
        self.assertEqual(status, 201, data)
        return data['id']

    def go_online(self, user=DRIVER, point=NEAR):
        status, data = self.driver('PUT', '/api/v1/driver/presence',
                                   {'latitude': point[0], 'longitude': point[1], 'available': True}, user)
        self.assertEqual(status, 200, data)
        return data

    # --------------------------------------------------------------
    def test_parcours_complet_et_historique(self):
        cid = self.create_course()
        self.go_online()

        _, offers = self.driver('GET', '/api/v1/driver/courses/available')
        offer = offers['courses'][0]
        self.assertEqual((offer['id'], offer['price'], offer['vehicle']), (cid, 12500, 'bus'))
        self.assertAlmostEqual(offer['distance_km'], 2.0, delta=0.6)

        status, snap = self.driver('POST', f'/api/v1/driver/courses/{cid}/accept',
                                   {'latitude': NEAR[0], 'longitude': NEAR[1]})
        self.assertEqual(status, 200, snap)
        self.assertEqual(snap['course']['driver_name'], 'Jean Mukendi')

        # Le client voit la vraie position du chauffeur.
        _, seen = self.client('GET', f'/api/v1/courses/{cid}/positions')
        self.assertEqual(seen['course']['status'], 'assigned')
        self.assertEqual((seen['positions']['driver']['latitude'],
                          seen['positions']['driver']['longitude']), NEAR)

        # Le chauffeur avance, le client partage sa position, les étapes s'enchaînent.
        self.driver('PUT', f'/api/v1/driver/courses/{cid}/position',
                    {'latitude': PICKUP[0], 'longitude': PICKUP[1]})
        self.client('PUT', f'/api/v1/courses/{cid}/position', {'latitude': -4.3218, 'longitude': 15.3126})
        for step in ('arrived', 'in_transit', 'delivered'):
            status, snap = self.driver('PUT', f'/api/v1/driver/courses/{cid}/status', {'status': step})
            self.assertEqual(status, 200, snap)

        # Historique en base : toutes les étapes, dans l'ordre, avec leur auteur.
        self.assertEqual([(h['status'], h['actor']) for h in self.db.history], [
            ('pending', 'client'), ('assigned', 'driver'), ('arrived', 'driver'),
            ('in_transit', 'driver'), ('delivered', 'driver')])
        arrived = self.db.history[2]
        self.assertEqual((arrived['latitude'], arrived['longitude']), PICKUP)

        # Chronologie renvoyée aux deux apps, historique des deux côtés.
        _, final = self.client('GET', f'/api/v1/courses/{cid}')
        self.assertEqual([t['status'] for t in final['timeline']],
                         ['pending', 'assigned', 'arrived', 'in_transit', 'delivered'])
        _, mine = self.client('GET', '/api/v1/courses')
        self.assertEqual(mine['courses'][0]['status'], 'delivered')
        _, done = self.driver('GET', '/api/v1/driver/courses/history')
        self.assertEqual(done['courses'][0]['id'], cid)

        # Après la livraison, plus aucune position acceptée.
        status, _ = self.driver('PUT', f'/api/v1/driver/courses/{cid}/position',
                                {'latitude': PICKUP[0], 'longitude': PICKUP[1]})
        self.assertEqual(status, 409)

    def test_un_seul_chauffeur_gagne_la_course(self):
        cid = self.create_course()
        self.go_online()
        self.go_online(OTHER_DRIVER)
        point = {'latitude': NEAR[0], 'longitude': NEAR[1]}
        self.assertEqual(self.driver('POST', f'/api/v1/driver/courses/{cid}/accept', point)[0], 200)
        status, _ = self.driver('POST', f'/api/v1/driver/courses/{cid}/accept', point, OTHER_DRIVER)
        self.assertEqual(status, 409)
        # Le perdant ne voit ni ne modifie la course.
        self.assertEqual(self.driver('GET', f'/api/v1/driver/courses/{cid}/positions',
                                     user=OTHER_DRIVER)[0], 404)
        self.assertEqual(self.driver('PUT', f'/api/v1/driver/courses/{cid}/status',
                                     {'status': 'arrived'}, OTHER_DRIVER)[0], 409)

    def test_chauffeur_hors_ligne_ou_trop_loin(self):
        cid = self.create_course()
        point = {'latitude': NEAR[0], 'longitude': NEAR[1]}
        # Sans présence récente : aucune offre, acceptation refusée.
        self.assertEqual(self.driver('GET', '/api/v1/driver/courses/available')[1], {'courses': []})
        self.assertEqual(self.driver('POST', f'/api/v1/driver/courses/{cid}/accept', point)[0], 409)
        # Trop loin (Lubumbashi).
        far = (-11.66, 27.48)
        self.go_online(point=far)
        self.assertEqual(self.driver('GET', '/api/v1/driver/courses/available')[1], {'courses': []})
        status, data = self.driver('POST', f'/api/v1/driver/courses/{cid}/accept',
                                   {'latitude': far[0], 'longitude': far[1]})
        self.assertEqual(status, 409)
        self.assertIn('15 km', data['message'])

    def test_annulation_par_le_client_dans_l_historique(self):
        cid = self.create_course()
        self.go_online()
        self.driver('POST', f'/api/v1/driver/courses/{cid}/accept', {'latitude': NEAR[0], 'longitude': NEAR[1]})
        status, data = self.client('POST', f'/api/v1/courses/{cid}/cancel')
        self.assertEqual((status, data['status']), (200, 'cancelled'))
        self.assertEqual(self.db.history[-1]['status'], 'cancelled')
        # Le chauffeur le voit à la lecture suivante, et ne peut plus avancer.
        _, snap = self.driver('GET', f'/api/v1/driver/courses/{cid}/positions')
        self.assertEqual(snap['course']['status'], 'cancelled')
        self.assertEqual(self.driver('PUT', f'/api/v1/driver/courses/{cid}/status',
                                     {'status': 'arrived'})[0], 409)
        # Une course récupérée ne s'annule plus.
        cid2 = self.create_course()
        self.go_online()
        self.driver('POST', f'/api/v1/driver/courses/{cid2}/accept', {'latitude': NEAR[0], 'longitude': NEAR[1]})
        self.driver('PUT', f'/api/v1/driver/courses/{cid2}/status', {'status': 'arrived'})
        self.driver('PUT', f'/api/v1/driver/courses/{cid2}/status', {'status': 'in_transit'})
        self.assertEqual(self.client('POST', f'/api/v1/courses/{cid2}/cancel')[0], 409)

    def test_etapes_dans_l_ordre_uniquement(self):
        cid = self.create_course()
        self.go_online()
        self.driver('POST', f'/api/v1/driver/courses/{cid}/accept', {'latitude': NEAR[0], 'longitude': NEAR[1]})
        self.assertEqual(self.driver('PUT', f'/api/v1/driver/courses/{cid}/status',
                                     {'status': 'delivered'})[0], 409)
        self.assertEqual(self.driver('PUT', f'/api/v1/driver/courses/{cid}/status',
                                     {'status': 'pending'})[0], 400)

    def test_acces_et_jetons(self):
        cid = self.create_course()
        # Sans jeton, jeton expiré, mauvais rôle : refusés.
        self.assertEqual(self.call('GET', '/api/v1/courses')[0], 401)
        self.assertEqual(self.call('GET', '/api/v1/courses', CLIENT, 'client', expired=True)[0], 401)
        self.assertEqual(self.call('GET', '/api/v1/driver/courses/available', CLIENT, 'client')[0], 401)
        self.assertEqual(self.call('GET', '/api/v1/courses', DRIVER, 'driver')[0], 401)
        # Un autre client ne voit ni ne déplace la course.
        self.assertEqual(self.client('GET', f'/api/v1/courses/{cid}', user=OTHER_CLIENT)[0], 404)
        self.assertEqual(self.client('PUT', f'/api/v1/courses/{cid}/position',
                                     {'latitude': 0, 'longitude': 0}, OTHER_CLIENT)[0], 403)

    def test_donnees_invalides(self):
        self.assertEqual(self.client('POST', '/api/v1/courses', {'pickup': 'A'})[0], 400)
        status, data = self.client('POST', '/api/v1/courses', {
            'pickup': 'A', 'dropoff': 'B', 'pickup_latitude': 0, 'pickup_longitude': 0,
            'destination_latitude': 1, 'destination_longitude': 1, 'cargo_type': 'X',
            'weight': 5, 'price': -10})
        self.assertEqual((status, data['message']), (400, 'Prix invalide.'))
        cid = self.create_course()
        self.assertEqual(self.client('PUT', f'/api/v1/courses/{cid}/position',
                                     {'latitude': 120, 'longitude': 0})[0], 400)


if __name__ == '__main__':
    unittest.main()
