import pandas as pd
df = pd.read_csv("records.csv")
print(df.columns.tolist())
sub = df[df.prototype_id.isin(["p_E05X2XJNTY"])] if "prototype_id" in df.columns else df
print(sub.head(30).to_string())