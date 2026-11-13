-- À exécuter UNE SEULE FOIS dans la console SQL Neon uniquement si
-- les comptes existants ont été créés lorsque la vérification était désactivée.
-- Cela obligera les développeurs déjà présents à vérifier leur adresse
-- au prochain accès. Ils pourront demander un code depuis la page de connexion.
UPDATE store_developerprofile
SET email_verified = FALSE,
    verification_code = '';

-- Contrôle : cette requête doit retourner 0 tant que les développeurs
-- concernés n'ont pas terminé leur vérification.
SELECT COUNT(*) AS profils_non_verifies
FROM store_developerprofile
WHERE email_verified = FALSE;
