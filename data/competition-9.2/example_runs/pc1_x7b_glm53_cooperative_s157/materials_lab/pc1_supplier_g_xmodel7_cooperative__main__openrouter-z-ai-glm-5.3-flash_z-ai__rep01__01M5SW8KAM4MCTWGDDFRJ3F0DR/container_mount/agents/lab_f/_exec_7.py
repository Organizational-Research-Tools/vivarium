import pandas as pd
df = pd.read_csv('records.csv')
# find composition columns
cols = [c for c in df.columns]
print(cols)
for pid in ['p_5XVCC7PF44','p_5XVCC7PF3G','p_MPZVZAYTMV']:
    sub = df[df.prototype_id==pid]
    if len(sub):
        r = sub.iloc[0]
        print(pid, [r[c] for c in cols if 'mod' in c.lower() or 'module' in c.lower()] if any('mod' in c.lower() for c in cols) else r.to_dict())