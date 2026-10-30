import pandas as pd
df = pd.read_csv('records.csv')
for p in ['p_P2FZ2H2S6A','p_P2FZ2H2S5Z']:
    q = df[df.prototype_id==p]
    print(p, q[['record_id','test','measured_by','value']].to_string(), q.project.unique())
# search any strength/water receipts near p_P2FZ2H2S* on QP-1586
m = df[df.record_id.str.startswith('r_P2FZ2H2S')]
print(m[['record_id','project','prototype_id','test','measured_by','value']].to_string())