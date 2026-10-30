df=pd.read_csv('records.csv')
prot=df.drop_duplicates('prototype_id')[['project','prototype_id']+list(df.columns[11:23])]
print(prot.to_string())