# Tako Transactions Service

## Description

Le **Tako Transactions Service** gère toutes les opérations liées aux courses (rides) et au suivi de la localisation des chauffeurs et des colis. Il est le cœur opérationnel de l'application Tako, permettant de coordonner les déplacements et d'assurer la visibilité en temps réel.

## Fonctionnalités

- **Gestion des courses** : Création, mise à jour et consultation des détails des courses.
- **Suivi de localisation** : Enregistrement et récupération des positions GPS des chauffeurs en temps réel.
- **Statuts de course** : Gestion des différents états d'une course (en attente, acceptée, en cours, terminée, annulée).
- **Historique des transactions** : Permet de consulter les courses passées.

## Architecture

Le service est développé en Python avec Flask et Flask-SQLAlchemy, et utilise MySQL comme base de données. Il suit une architecture modulaire :

```text
transactions_service/
├── app.py              # Point d'entrée principal de l'application Flask
├── requirements.txt    # Dépendances Python
└── src/
    ├── __init__.py
    ├── models/         # Définition des modèles de données (ex: Ride, DriverLocation)
    │   ├── ride_model.py
    │   └── driver_location_model.py
    ├── routes/         # Définition des routes API pour les transactions et la localisation
    │   └── transactions_routes.py
    └── services/       # Logique métier et interaction avec les modèles
        └── transactions_service.py
```

## Configuration

La connexion à la base de données MySQL est configurée dans `app.py`:

```python
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+mysqlconnector://user:password@db/transactions_db"
```

Il est essentiel de remplacer `user`, `password`, et `db` par les informations d'identification et l'adresse de votre serveur MySQL. En production, utilisez des variables d'environnement pour ces informations sensibles.

## Installation et Exécution (Développement)

1.  **Cloner le dépôt** :
    ```bash
    git clone https://github.com/Bbondong/tako-transactions-service.git
    cd tako-transactions-service
    ```

2.  **Créer un environnement virtuel et installer les dépendances** :
    ```bash
    python -m venv venv
    source venv/bin/activate  # Sur Windows: .\venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Lancer le service** :
    ```bash
    python app.py
    ```
    Le service sera accessible sur `http://localhost:5002`.

## Endpoints API

-   `GET /` : Health check du service Transactions.
-   `POST /rides` : Crée une nouvelle course.
    -   **Requête** : `{"passenger_id": 1, "start_location_lat": 48.8566, "start_location_lon": 2.3522}`
-   `GET /rides/<int:ride_id>` : Récupère les détails d'une course spécifique.
-   `POST /driver_location` : Met à jour la localisation d'un chauffeur.
    -   **Requête** : `{"driver_id": 101, "latitude": 48.8584, "longitude": 2.2945}`
-   `GET /driver_location/<int:driver_id>` : Récupère la dernière localisation connue d'un chauffeur.

## Déploiement

Pour un déploiement en production, il est recommandé d'utiliser Docker et un serveur WSGI comme Gunicorn. Un `Dockerfile` sera ajouté ultérieurement pour faciliter ce processus.

## Contribution

Les contributions sont les bienvenues. Veuillez suivre les directives de contribution et soumettre des pull requests.

## Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.
