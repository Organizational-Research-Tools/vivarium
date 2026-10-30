import pandas as pd
df=pd.read_csv('records.csv')
for p in ["p_FRY0EA0DNZ","p_B0A2AF9B7E","p_W9QVRJ7PXQ","p_G8S61Z3JR7","p_W9QVRJ7PXS"]:
    sub=df[(df.prototype_id==p)&(df.test=='heat')&(df.kind=='qualification')] if 'kind' in df else df[(df.prototype_id==p)&(df.test=='heat')]
    print(p, len(sub), sub.value.mean() if len(sub) else None)
print(df.columns.tolist())