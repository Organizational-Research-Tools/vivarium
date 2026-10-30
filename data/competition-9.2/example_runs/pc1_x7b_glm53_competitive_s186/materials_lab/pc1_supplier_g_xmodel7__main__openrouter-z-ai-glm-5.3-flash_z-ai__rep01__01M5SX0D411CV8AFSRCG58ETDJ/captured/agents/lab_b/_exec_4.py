import pandas as pd
df = pd.read_csv('records.csv')
# RTK family = QP-5993 recipes with surface 6XS or conditioning A6U
for pat,name in [(('6XS',), '6XS-surface QP-5993'), (('A6U',), 'A6U-conditioning QP-5993')]:
    sub = df[(df.project=='QP-5993') & (df.property=='strength')]
    for col in df.columns:
        pass
    mask = sub.apply(lambda r: pat[0] in str(r.values), axis=1)
    print(name)
    print(sub[mask][['prototype_id','value','measured_by']].to_string())
    print()
