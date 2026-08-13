-- Optional psql bootstrap. The Python command `python main.py init-db` is preferred.
-- Usage:
--   psql -v target_database=agro_platform -d postgres -f sql/000_create_database.sql
SELECT format('CREATE DATABASE %I', :'target_database')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = :'target_database'
)\gexec

