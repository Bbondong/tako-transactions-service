# Tako Transactions Service

Service dédié aux **courses** : création par le client, offres aux
chauffeurs proches, acceptation, suivi GPS des deux côtés, étapes de
livraison, annulation, et **historique conservé en base**.

Il partage la base MySQL de `tako-auth-service` (tables `courses`,
`course_positions`, `driver_presence`, `user`) et accepte les jetons JWT
qu'il émet : aucune session n'est créée ici.

## Configuration

Copier le `.env` de `tako-auth-service` (il n'est jamais commité) :

| Variable | Rôle |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | base commune |
| `TAKO_JWT_SECRET` | même secret que l'auth-service (vérification des jetons) |
| `TAKO_CLIENT_ROLE_ID`, `TAKO_DRIVER_ROLE_ID` | rôles `id_tpcompte` client et chauffeur |
| `TAKO_API_KEY` | clé interne envoyée par la Gateway (`X-Internal-Key`) |
| `CLOUDINARY_*` | envoi de la photo de la marchandise |

`TAKO_DRIVER_ROLE_ID` est obligatoire pour toutes les routes chauffeur.

## Installation

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python migrate.py      # crée la table d'historique (idempotent)
.venv/bin/python app.py          # http://localhost:5002
```

Côté Gateway : `TRANSACTIONS_SERVICE_URL` doit pointer vers ce service.
Les apps l'appellent sous `/transactions/…` avec la clé client.

## Historique

`course_status_history` reçoit une ligne à chaque étape — création
(`pending`), acceptation (`assigned`), arrivée (`arrived`), départ
(`in_transit`), livraison (`delivered`), annulation (`cancelled`) — avec
l'acteur, son compte, la position et l'heure. Les lignes ne sont jamais
modifiées. Chaque réponse de course renvoie cette chronologie
(`timeline`).

## Routes (préfixe `/api/v1`)

Client (jeton client) :

- `POST /courses` — créer une course (prix et véhicule fournis par l'app)
- `GET /courses` — historique du client
- `GET /courses/<id>` ou `/courses/<id>/positions` — course, positions, chronologie
- `PUT /courses/<id>/position` — position GPS du client
- `POST /courses/<id>/cancel` — annuler (avant récupération du colis)

Chauffeur (jeton chauffeur) :

- `PUT /driver/presence` — en ligne / hors ligne avec position (toutes les < 30 s)
- `GET /driver/courses/available` — offres à moins de 15 km
- `POST /driver/courses/<id>/accept` — accepter (un seul chauffeur gagne)
- `GET /driver/courses/active` — course en cours
- `GET /driver/courses/history` — courses du chauffeur
- `GET /driver/courses/<id>/positions` — course, positions, chronologie
- `PUT /driver/courses/<id>/position` — position GPS du chauffeur
- `PUT /driver/courses/<id>/status` — `arrived` → `in_transit` → `delivered`

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```
