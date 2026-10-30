import pandas as pd
df = pd.read_csv("records.csv")
print(df.project.unique())
sub = df[df.project.astype(str).str.contains("8476")]
print(len(sub), sub.kind.unique())
print(sub.head(3).to_string())