import pandas as pd
df = pd.read_csv("records.csv")
df = df[df.kind=="qualification"]
for t,thr in [("seal hold temperature",77.5),("edge crush resistance",7.1),("wet strength retained",78.0)]:
    g = df[df.test==t].groupby("prototype_id")["value"].agg(["mean","count"])
    g = g[g["count"]>=6]
    print(t, len(g), "passing:", (g["mean"]>=thr).sum())
    if t=="wet strength retained":
        print(g.sort_values("mean",ascending=False).head(20).to_string())
