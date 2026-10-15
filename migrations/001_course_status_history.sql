-- Historique des courses : chaque étape (création, acceptation, arrivée,
-- départ, livraison, annulation) est ajoutée, jamais modifiée ni effacée.
-- Dépend des tables de l'auth-service : courses (001), course_positions
-- (002) et driver_presence (004), dans la même base.
CREATE TABLE IF NOT EXISTS course_status_history (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  course_id BIGINT NOT NULL,
  status VARCHAR(30) NOT NULL,
  actor ENUM('client', 'driver') NOT NULL,
  user_id BIGINT NOT NULL,
  latitude DECIMAL(10,7) NULL,
  longitude DECIMAL(10,7) NULL,
  created_at TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  INDEX idx_history_course (course_id, created_at),
  CONSTRAINT fk_history_course FOREIGN KEY (course_id)
    REFERENCES courses(id) ON DELETE CASCADE
);

-- Courses existantes : leur création devient la première étape connue.
INSERT INTO course_status_history (course_id, status, actor, user_id, latitude, longitude, created_at)
SELECT c.id, 'pending', 'client', c.user_id, c.pickup_latitude, c.pickup_longitude, c.created_at
FROM courses c
WHERE NOT EXISTS (SELECT 1 FROM course_status_history h WHERE h.course_id = c.id);
