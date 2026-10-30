import pandas as pd, itertools
df = pd.read_csv('records.csv')
w = df[(df.instrument=='water')]
protos = {
'p_N2GHR30FF4':["ZY6","LB3","Y9V","Y7L","Q7S","5B8","RF3","X9Z","G4B","WN7","34U","7MP"],
'p_N2GHR30FF6':["NF2","YH6","93H","X2P","E8S","29B","8Q7","T8R","A7P","9B8","FA3","W5T"],
'p_C2Q7ZKXA17':["TL4","TU4","KX7","QE3","6DD","8P4","3JQ","5UV","3CV","BX9","G7L","3DC"],
'p_C2Q7ZKXA19':["8Z2","N2L","Y9V","FZ6","RB3","6UD","2WG","LR4","5J9","VR3","P4U","9VC"],
'p_C2Q7ZKXA1B':["ZY6","YH6","93H","Y7L","6DD","29B","8Q7","X9Z","G4B","BX9","34U","W5T"],
'p_C2Q7ZKXA1D':["NF2","TU4","KX7","X2P","RB3","8P4","2WG","T8R","A7P","WN7","FA3","3DC"],
'p_C2Q7ZKXA1F':["TL4","N2L","Y9V","QE3","E8S","6UD","RF3","5UV","5J9","9B8","G7L","9VC"],
'p_C2Q7ZKXA1H':["8Z2","LB3","93H","FZ6","Q7S","5B8","3JQ","LR4","3CV","VR3","P4U","7MP"],
'p_C2Q7ZKXA1K':["ZY6","TU4","Y9V","X2P","Q7S","29B","RF3","T8R","G4B","BX9","34U","3DC"],
'p_C2Q7ZKXA1N':["NF2","N2L","93H","Y7L","E8S","8P4","8Q7","5UV","A7P","WN7","FA3","9VC"],
'p_C2Q7ZKXA1Q':["TL4","LB3","KX7","QE3","6DD","5B8","3JQ","X9Z","3CV","9B8","G7L","W5T"],
'p_RGR39DTB91':["8Z2","YH6","Y9V","FZ6","RB3","6UD","2WG","LR4","5J9","VR3","P4U","9VC"],
'p_RGR39DTB93':["ZY6","LB3","93H","QE3","Q7S","29B","RF3","X9Z","G4B","WN7","34U","7MP"],
'p_RGR39DTB95':["NF2","YH6","KX7","Y7L","E8S","8P4","8Q7","T8R","A7P","9B8","FA3","W5T"],
'p_RGR39DTB97':["TL4","TU4","Y9V","X2P","6DD","6UD","3JQ","5UV","3CV","BX9","G7L","3DC"],
'p_RGR39DTB99':["8Z2","N2L","93H","FZ6","RB3","5B8","2WG","LR4","5J9","VR3","P4U","9VC"],
'p_RGR39DTB9B':["ZY6","TU4","KX7","Y7L","Q7S","8P4","8Q7","X9Z","G4B","BX9","34U","3DC"],
'p_RGR39DTB9D':["NF2","LB3","Y9V","X2P","E8S","5B8","2WG","T8R","A7P","WN7","FA3","9VC"],
'p_RGR39DTB9F':["TL4","N2L","93H","QE3","6DD","29B","RF3","5UV","3CV","9B8","G7L","7MP"],
'p_RGR39DTB9H':["8Z2","YH6","KX7","FZ6","Q7S","6UD","3JQ","LR4","5J9","VR3","P4U","W5T"],
'p_RGR39DTB9K':["ZY6","YH6","93H","FZ6","6DD","29B","3JQ","X9Z","5J9","BX9","G7L","7MP"],
'p_ATJNRX81K5':["NF2","TU4","KX7","Y7L","Q7S","6UD","RF3","5UV","A7P","WN7","FA3","3DC"],
'p_ATJNRX81K7':["TL4","LB3","93H","QE3","E8S","8P4","8Q7","X9Z","3CV","9B8","FA3","9VC"],
'p_ATJNRX81K9':["8Z2","N2L","Y9V","X2P","RB3","5B8","2WG","T8R","G4B","BX9","P4U","W5T"],
}
mods=["base","sec","binder","add1","add2","add3","pp1","pp2","pp3","surf","joint","cond"]
rows=[]
for pid,rec in protos.items():
    sub=w[w.prototype_id==pid]
    if len(sub)==0: continue
    rows.append(rec+[sub.value.mean()])
d=pd.DataFrame(rows,columns=mods+['y'])
for m in mods:
    print(d.groupby(m).y.mean().sort_values(ascending=False).to_dict())
