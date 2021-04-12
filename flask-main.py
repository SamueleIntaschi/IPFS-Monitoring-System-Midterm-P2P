from flask import Flask, redirect, render_template, request, make_response
from flask_wtf import FlaskForm
import wtforms as f
from wtforms import Form
from forms import DownloadForm
import requests
import threading
import plotly
import plotly.graph_objs as go
import pandas as pd
import json
import signal
import sys
import ndjson
import plotly.express as px

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ANOTHER ONE'
known_peers = []
collaborating_peers = []
#file_downloaded = 
# 0 if no file is in downloading
# 1 if the file is in downloading
# 2 if the file is downloaded
file_downloaded = 0

def signal_handler(sig, frame):
    print('Cleaning the downloaded blocks...')
    url = 'http://127.0.0.1:5001/api/v0/repo/gc'
    res = requests.post(url)
    if res.status_code == 200:
        print("Blocks cleaned")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def get_file(file_cid):
    '''
    Start file download
    '''
    global file_downloaded
    file_downloaded = 1
    #Save the current state of the known peers
    check_known_peers()
    print("Trying to download "+file_cid )
    url = 'http://127.0.0.1:5001/api/v0/get?arg=' + str(file_cid) + '&output=.'
    res = requests.post(url)
    if res.status_code == 200:
        file_downloaded = 2
    else:
        file_downloaded = 0

def compute_peer_metrics(peer):
    '''
    Check if a peer is already known by the system and in that case check if that peer has sent more data, then compute the values.
    If the peer is already known and has not sent more data ignore it.
    '''
    global collaborating_peers
    found = False
    for p in collaborating_peers:
        #Update the existing peer
        if (peer['Peer'] == p['Peer']):
            if peer['Exchanged'] > p['Exchanged']:
                p['Bytes_received'] = peer['Bytes_received']
                p['Bytes_sent'] = peer['Bytes_sent']
                p['Exchanged'] = peer['Exchanged']
            found = True
            break
    #If the peer is not in the collaborating peers, search it in the previously known peers
    if found == False:
        for p in known_peers:
            #If something has changed in known peers means that the peer has sent more data
            if (peer['Peer'] == p['Peer']):
                #if ((peer['Bytes_sent'] > p['Bytes_sent']) or (peer['Bytes_received'] > p['Bytes_received']) or (peer['Value'] != p['Value'])):
                if peer['Exchanged'] > p['Exchanged']:
                    country, ip = who_is_peer(p['Peer'])
                    info = {
                        'Peer':p['Peer'],
                        'Bytes_sent':peer['Bytes_sent'] - p['Bytes_sent'],
                        'Bytes_received':peer['Bytes_received'] - p['Bytes_received'],
                        'Value':peer['Value'],
                        'Exchanged':peer['Exchanged'] - p['Exchanged'],
                        'IP_address':ip,
                        'Country':country
                    }
                    collaborating_peers.append(info)
                found = True
                break
    #If it is the first time that we encounter the peer, add it to the collaborating peers
    if found == False:
        country, ip = who_is_peer(peer['Peer'])
        peer['IP_address'] = ip
        peer['Country'] = country
        collaborating_peers.append(peer)

def check_known_peers():
    '''
    Save known peers before downloading the file
    '''
    global known_peers
    global collaborating_peers
    #Reset known peers
    known_peers = []
    #Reset collaborating peers
    collaborating_peers = []
    res =  requests.post('http://127.0.0.1:5001/api/v0/bitswap/stat')
    peers = res.json()['Peers']
    for peer in peers:
        #Query the bitswap agent ledger for peer informations
        string = 'http://127.0.0.1:5001/api/v0/bitswap/ledger?arg='+str(peer)
        restmp = requests.post(string)
        peer_infos = restmp.json()
        #If the peer has no data exchanged, ignore it, else add it to the collaborating peers
        if (peer_infos['Exchanged'] > 0):
            known_peers.append({
                'Peer':peer_infos['Peer'],
                'Bytes_sent':peer_infos['Sent'],
                'Bytes_received':peer_infos['Recv'],
                'Value':peer_infos['Value'],
                'Exchanged':peer_infos['Exchanged']
            })
    print('Known peers:')
    for elem in known_peers:
        print(elem)

def clean_ip_addresses(ips):
    '''
    Remove the addresses that are probably private and the duplicates
    '''
    ip_addrs = []
    for ip in ips:
        ip_addr = ip.split('/')[2]
        if(ip_addr[0:3] != '127' and ip_addr[0:3] != '192' and ip_addr[0:3] != '::1' 
            and (ip_addr[0:2] != '2' and ip_addr[4] != ':') and ip_addr[0:2] != '10' and ip_addr[0:3] != '172'):
            if (ip_addr) not in ip_addrs:
                ip_addrs.append(ip_addr)
    return ip_addrs

def who_is_peer(peer):
    '''
    Search the multiaddresses of a peer and his country
    '''
    url = 'http://127.0.0.1:5001/api/v0/dht/findpeer?arg='+str(peer)
    restmp = requests.post(url)
    results = restmp.json(cls=ndjson.Decoder)
    for result in results:
        responses = result["Responses"]
        if responses is not None:
            for res in responses:
                addrs = res['Addrs']
                ip_addrs = clean_ip_addresses(addrs)
                if len(ip_addrs) == 1:
                    ip = ip_addrs[0]
                    url = "http://api.hostip.info/get_html.php?ip=" + ip + "&position=true"
                    res = requests.get(url)
                    text = res.text
                    txt = text.split('\n')
                    country = txt[0].split(': ')[1]
                    name_parts = country.split(' ')
                    initials = name_parts[len(name_parts)-1]
                    if initials != '(XX)':
                        country_name = country.split(' (')[0]
                        return (country_name, ip)
                    else:
                        return ('Unknown Country', ip)
    return (None, None)

                    
def check_collaborating_peers():
    '''
    Check the peers who are collaborating with my node to download the file
    '''
    #Get all the partners
    res =  requests.post('http://127.0.0.1:5001/api/v0/bitswap/stat')
    peers = res.json()['Peers']
    for peer in peers:
        #Query the bitswap agent for the ledger for peer informations
        url = 'http://127.0.0.1:5001/api/v0/bitswap/ledger?arg='+str(peer)
        restmp = requests.post(url)
        peer_infos = restmp.json()
        if (peer_infos['Exchanged'] > 0):
            info = {
                'Peer':peer_infos['Peer'],
                'Bytes_sent':peer_infos['Sent'],
                'Bytes_received':peer_infos['Recv'],
                'Value':peer_infos['Value'],
                'Exchanged':peer_infos['Exchanged']
            }
            compute_peer_metrics(info)
    print('Collaborating peers:')
    for elem in collaborating_peers:
        print(elem)

def create_plot():
    '''
    Create the plots and return the json of them
    '''
    #Update the list of collaborating peers
    check_collaborating_peers()
    peer_ids = []
    bytes_received = []
    exchanged_blocks = []
    peers = collaborating_peers
    for p in peers:
        peer_ids.append(p['IP_address'])
        bytes_received.append(p['Bytes_received'])
        exchanged_blocks.append(p['Exchanged'])
    data_dict = dict()
    data_dict = {
        'Peer_ids':peer_ids,
        'Bytes_received':bytes_received,
        'Exchanged_blocks':exchanged_blocks
    }
    df = pd.DataFrame.from_dict(data_dict)
    #df = pd.DataFrame({'x': x, 'y': y}) # creating a sample dataframe
    trace1 = go.Bar(
        x = df['Peer_ids'],
        y = df['Bytes_received'],
        name = 'Bytes received',
        marker = dict(color = 'rgba(255, 174, 255, 0.5)', line=dict(color='rgb(0,0,0)',width=1.5))
    )
    trace2 = go.Bar(
        x = df['Peer_ids'],
        y = df['Exchanged_blocks'],
        name = 'Exchanged blocks',
        marker = dict(color = 'rgba(255, 255, 128, 0.5)', line=dict(color='rgb(0,0,0)',width=1.5))
    )
    countries = dict()
    #Count peers for country
    for peer in peers:
        country = peer['Country']
        if country is not None and country != 'Unknown Country':
            if country in countries:
                countries[country] = countries[country] + 1
            else:
                countries[country] = 1
    cs = []
    ps = []
    for country in countries:
        cs.append(country)
        ps.append(countries[country])
    #Bubble map countries
    dfmap = pd.DataFrame.from_dict(dict(Countries=cs, Peers=ps))
    print(dfmap)
    maps = go.Scattergeo(
        locationmode = 'country names',
        locations = dfmap["Countries"],
        text = dfmap['Peers'],
        mode = 'markers',
        name = 'Map',
        marker = dict(
            size = dfmap['Peers'] * (200 / dfmap['Peers'].max()),
            opacity = 0.8,
            reversescale = False,
            autocolorscale = False,
            line = dict(
                width=1,
                color='rgba(102, 102, 102)'
            ),
            colorscale = [[0, 'rgb(253, 174, 107)'], [0.5, 'rgb(241, 105, 19)'], [1.0, 'rgb(166, 54, 3)']],
            cmin = 0,
            color = dfmap['Peers'],
            cmax = dfmap['Peers'].max(),
            colorbar_title="N° peers"
        )
    )
    data1 = [trace1]
    data1j = json.dumps(data1, cls=plotly.utils.PlotlyJSONEncoder)
    data2 = [trace2]
    data2j = json.dumps(data2, cls=plotly.utils.PlotlyJSONEncoder)
    data3 = [maps]
    data3j = json.dumps(data3, cls=plotly.utils.PlotlyJSONEncoder)
    array = [data1j, data2j, data3j]
    return array

@app.route('/', methods=['GET','POST'])
def index():
    '''
    Index function
    '''
    global file_downloaded
    form = DownloadForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            file_cid = request.form['file_cid']
            #Start file download in another thread to not wait the response
            thread = threading.Thread(target=get_file,args=(file_cid,))
            thread.start()
            return render_template('plot.html', file_cid=file_cid)
        #else error 
    else:
        file_downloaded = 0
        return render_template('index.html', form=form)

@app.route('/plots')
def update_plot():
    '''
    Updates the plot and return them in json format
    '''
    plots = create_plot()
    return json.dumps(plots)

@app.route('/file')
def file_info():
    '''
    Communicates the state of the file download
    '''
    return json.dumps(file_downloaded)

if __name__ == '__main__':
    app.run()

    