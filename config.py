import os

class Config:
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')   # This will be your SERVICE ROLE key (for backend admin)
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
