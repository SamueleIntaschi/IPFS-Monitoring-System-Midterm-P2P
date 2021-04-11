from flask import Flask, redirect, render_template, request, make_response
from flask_wtf import FlaskForm
import wtforms as f
from wtforms import Form
from forms import DownloadForm
import time
import requests
import threading
import plotly
import plotly.graph_objs as go
import pandas as pd
import numpy as np
import json
import signal
import sys
import ndjson
import plotly.express as px

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ANOTHER ONE'
known_peers = []

def signal_handler(sig, frame):
    print('Clean and stop')
    url = 'http://127.0.0.1:5001/api/v0/repo/gc'
    res = requests.post(url)
    print(res)
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def get_file(file_cid):
    '''
    TODO
    '''
    known_peers = check_known_peers()
    print("Trying to download "+file_cid )
    url = 'http://127.0.0.1:5001/api/v0/get?arg=' + str(file_cid) + '&output=./'
    res = requests.post(url)
    print(res.text)

def compute_peer_metrics(peer, known_peers):
    '''
    Check if a peer is already known by the system and in that case check if that peer has sent more data, then compute the values.
    If the peer is already known and has not sent more data ignire it.
    '''
    for p in known_peers:
        #If something has changed in known peers means that the peer has sent more data
        if (peer['Peer'] == p['Peer']):
            #if ((peer['Bytes_sent'] > p['Bytes_sent']) or (peer['Bytes_received'] > p['Bytes_received']) or (peer['Value'] != p['Value'])):
            if peer['Exchanged'] > p['Exchanged']:
                info = {
                    'Peer':p['Peer'],
                    'Bytes_sent':peer['Bytes_sent'] - p['Bytes_sent'],
                    'Bytes_received':peer['Bytes_received'] - p['Bytes_received'],
                    'Value':peer['Value'],
                    'Exchanged':peer['Exchanged'] - p['Exchanged']
                }
                return info
            else:
                return None
    return peer


def check_known_peers():
    '''
    Save known peers before downloading the file
    '''
    #Reset known peers
    known_peers = []
    res =  requests.post('http://127.0.0.1:5001/api/v0/bitswap/stat')
    peers = res.json()['Peers']
    collaborating_peers = []
    for peer in peers:
        #Query the bitswap agent ledger for peer informations
        string = 'http://127.0.0.1:5001/api/v0/bitswap/ledger?arg='+str(peer)
        restmp = requests.post(string)
        peer_infos = restmp.json()
        #If the peer has no data exchanged, ignore it, else add it to the collaborating peers
        if (peer_infos['Exchanged'] > 0):
            collaborating_peers.append({
                'Peer':peer_infos['Peer'],
                'Bytes_sent':peer_infos['Sent'],
                'Bytes_received':peer_infos['Recv'],
                'Value':peer_infos['Value'],
                'Exchanged':peer_infos['Exchanged']
            })
    print('Known peers:')
    for elem in collaborating_peers:
        print(elem)
    return collaborating_peers

def who_is_peer(peer):
    url = 'http://127.0.0.1:5001/api/v0/dht/findpeer?arg='+str(peer)
    restmp = requests.post(url)
    results = restmp.json(cls=ndjson.Decoder)
    for result in results:
        responses = result["Responses"]
        if responses is not None:
            for res in responses:
                addrs = res['Addrs']
                for addr in addrs:
                    print(addr)

def check_collaborating_peers():
    '''
    Check the peers who are collaborating with my node to download the file
    '''
    res =  requests.post('http://127.0.0.1:5001/api/v0/bitswap/stat')
    peers = res.json()['Peers']
    collaborating_peers = []
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
            peer_to_add = compute_peer_metrics(info, known_peers)
            if peer_to_add is not None:
                collaborating_peers.append(peer_to_add)
                who_is_peer(peer)
    print('Collaborating peers:')
    for elem in collaborating_peers:
        print(elem)
    return collaborating_peers

def create_plot(peers):
    peer_ids = []
    bytes_received = []
    exchanged_blocks = []
    for p in peers:
        peer_ids.append(p['Peer'])
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
    data1 = [trace1]
    data1j = json.dumps(data1, cls=plotly.utils.PlotlyJSONEncoder)
    data2 = [trace2]
    data2j = json.dumps(data2, cls=plotly.utils.PlotlyJSONEncoder)
    array = [data1j, data2j]
    #graphJSON = json.dumps(array, cls=plotly.utils.PlotlyJSONEncoder)
    return array

@app.route('/', methods=['GET','POST'])
def index():
    form = DownloadForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            file_cid = request.form['file_cid']
            #Start file download in another thread to not wait the response
            thread = threading.Thread(target=get_file,args=(file_cid,))
            thread.start()
            #time.sleep(5)
            peers = check_collaborating_peers()
            bar = create_plot(peers)
            return render_template('plot.html', plot=bar, file_cid=file_cid)
        #else error 
    else:
        return render_template('index.html', form=form)

@app.route('/plots')
def update_plot():
    peers = check_collaborating_peers()
    plots = create_plot(peers)
    return json.dumps(plots)

@app.route('/ipfs/file/get/<file_cid>')
def get_file(file_cid):
    #Save the current state of the known peers
    known_peers = check_known_peers()
    print("Trying to download "+file_cid )
    url = 'http://127.0.0.1:5001/api/v0/get?arg=' + str(file_cid) + '&encoding=json'
    res = requests.post(url)
    print(res)

@app.route('/ipfs/peers')
def peers():
    return check_collaborating_peers(known_peers)

if __name__ == '__main__':
    app.run()

    