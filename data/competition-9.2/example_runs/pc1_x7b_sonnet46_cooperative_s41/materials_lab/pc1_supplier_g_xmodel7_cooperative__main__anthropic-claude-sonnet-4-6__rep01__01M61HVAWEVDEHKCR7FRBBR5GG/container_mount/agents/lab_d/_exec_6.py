
import pandas as pd

df = pd.read_csv('records.csv')

# Find all prototype IDs and their projects, and what panels exist
proto_info = df.groupby(['prototype_id','project']).agg(
    measured_by=('measured_by', lambda x: x.iloc[0]),
    has_heat=('test', lambda x: 'seal hold temperature' in x.values),
    has_strength=('test', lambda x: 'edge crush resistance' in x.values),
    has_water=('test', lambda x: 'wet strength retained' in x.values),
    my_heat=('measured_by', lambda x: any(v == 'lab_d' and 
             df.loc[x.index,'test'].iloc[i] == 'seal hold temperature' 
             for i, v in enumerate(x))),
    kind=('kind', 'first'),
    secondary_sheet=('secondary_sheet', lambda x: x.dropna().iloc[0] if x.dropna().any() else None),
    requester=('requester', lambda x: x.iloc[0])
).reset_index()

print("All prototype IDs available (sorted by project):")
print(proto_info[['prototype_id','project','requester','measured_by','has_heat','has_strength','has_water','secondary_sheet']].to_string())
print()

# What unique prototypes are in the system?
all_protos = df.drop_duplicates('prototype_id')[['prototype_id','project','requester']]
print(f"\nTotal unique prototypes: {len(all_protos)}")
print(all_protos.sort_values('project').to_string())
