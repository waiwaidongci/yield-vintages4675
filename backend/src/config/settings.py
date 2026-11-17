import os,json
from pathlib import Path
_candidates=[Path(os.environ['PROJECT_JSON']) if os.getenv('PROJECT_JSON') else None,Path('/app/project.json'),Path(__file__).resolve().parents[2]/'project.json']
CONFIG=json.loads(next(p for p in _candidates if p and p.exists()).read_text())
DATABASE_URL=os.environ['DATABASE_URL']
REDIS_URL=os.getenv('REDIS_URL','redis://redis:6379/0')
SECRET=os.environ['JWT_SECRET']
