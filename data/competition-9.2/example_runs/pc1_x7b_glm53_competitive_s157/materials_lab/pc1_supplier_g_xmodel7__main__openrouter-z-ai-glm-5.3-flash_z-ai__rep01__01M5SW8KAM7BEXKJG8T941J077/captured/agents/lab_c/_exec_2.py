import pandas as pd
df = pd.read_csv("records.csv")
q = df[df.kind=="qualification"]
g = q.groupby(["prototype_id","test"]).agg(mean=("value","mean")).reset_index()
pivot = g.pivot(index="prototype_id", columns="test", values="mean")
print(pivot.to_string())
