from flask import Flask

from securite.securite import init_security
from src.routes.client_courses import client_courses_bp
from src.routes.driver_courses import driver_courses_bp

app = Flask(__name__)

# Même protection que l'auth-service : la Gateway passe avec sa clé interne,
# les appels directs sont filtrés (limite de débit, pare-feu).
init_security(app)

app.register_blueprint(client_courses_bp)
app.register_blueprint(driver_courses_bp)


@app.get('/')
def health():
    return {'status': 'ok', 'service': 'tako-transactions-service'}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
