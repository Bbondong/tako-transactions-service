"""Vérification des jetons émis par l'auth-service (même secret, mêmes rôles).

Le service des transactions ne crée aucune session : il accepte les jetons
client (connexion par code) et chauffeur (connexion par mot de passe)
signés par tako-auth-service, et vérifie le compte dans la base commune.
"""
import os
from functools import wraps

import jwt
from flask import g, jsonify, request

from src.data import fetch_one


def _secret():
    secret = os.getenv('TAKO_JWT_SECRET')
    if not secret or len(secret) < 32:
        raise RuntimeError('TAKO_JWT_SECRET must contain at least 32 characters')
    return secret


def _role_id(name):
    value = os.getenv(name)
    if not value or not value.isdigit():
        raise RuntimeError(f'{name} must match an existing role in id_tpcompte')
    return int(value)


def client_role():
    return _role_id('TAKO_CLIENT_ROLE_ID')


def driver_role():
    role = _role_id('TAKO_DRIVER_ROLE_ID')
    if role == client_role():
        raise RuntimeError('TAKO_DRIVER_ROLE_ID must be distinct from TAKO_CLIENT_ROLE_ID')
    return role


def _bearer_subject(role):
    """Identifiant du compte si le jeton est valide pour [role], sinon None."""
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return None
    try:
        claims = jwt.decode(header[7:], _secret(), algorithms=['HS256'],
                            options={'require': ['sub', 'exp', 'iat']})
        user_id = int(claims['sub'])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        return None
    if user_id <= 0 or claims.get('role') != role:
        return None
    return user_id


def client_authenticated(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = _bearer_subject('client')
        if user_id is None:
            return jsonify(message='Session expirée ou invalide.'), 401
        if not fetch_one('SELECT id_user FROM user WHERE id_user=%s AND id_tpcompte=%s AND active=1',
                         (user_id, client_role())):
            return jsonify(message='Compte introuvable.'), 401
        g.user_id = user_id
        return fn(*args, **kwargs)
    return wrapper


def driver_authenticated(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = _bearer_subject('driver')
        if user_id is None:
            return jsonify(message='Session chauffeur expirée ou invalide.'), 401
        if not fetch_one('SELECT id_user FROM user WHERE id_user=%s AND id_tpcompte=%s',
                         (user_id, driver_role())):
            return jsonify(message='Compte chauffeur introuvable.'), 401
        g.user_id = user_id
        return fn(*args, **kwargs)
    return wrapper
