#Flask imports
from flask import Flask, redirect, render_template, request, make_response
from flask_wtf import FlaskForm
import wtforms as f
from wtforms import Form
from forms import DownloadForm
#To make http requests
import requests
#To get timestamps
import datetime
#To manage the thread that perform the downlaod
import threading
#To handle SIGINT
import signal
import sys
#To encode and decode the HTTP messages
import json
import ndjson
#To create plots
import plotly
import plotly.graph_objs as go
import pandas as pd

#Flask setup
app = Flask(__name__)
app.config['SECRET_KEY'] = 'ANOTHER ONE'
#Variable that stores the CID of the content that is being downloaded
file_cid = ''
#Information about the peers known when the download starts
known_peers = []
#Information about the peers that are collaborating to the download of the file
collaborating_peers = []
#Information about the number of total peers and collaborating peers with the timestamp of the survey
peers_number = dict()
peers_number = {
    'n_peers':[],
    'times':[],
    'c_peers':[]
}
#Information about the actual and average incoming bandwidth with the timestamp of the survey
bw = dict()
bw = {
    'actual_in':[],
    'avg_in':[],
    'times':[]
}
#file_downloaded can be 
# 0 if no file is being downloaded
# 1 if the file is being downloaded
# 2 if the file is fully downloaded
file_downloaded = 0

def signal_handler(sig, frame):
    '''
    When a signal is received it starts the cleanup of the blocks downloaded until now
    '''
    print('Cleaning the downloaded blocks...')
    #Sending an ipfs repo gc request
    url = 'http://127.0.0.1:5001/api/v0/repo/gc'
    res = requests.post(url)
    if res.status_code == 200:
        print("Blocks cleaned")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def get_file(file_cid):
    '''
    Starts the download of a file
    '''
    global file_downloaded
    #Setting the variable that indicates that a file is being downloaded
    file_downloaded = 1
    #Saving the current state of the known peers
    check_known_peers()
    print("Trying to download "+file_cid )
    #Sending an ipfs get request to start the download
    url = 'http://127.0.0.1:5001/api/v0/get?arg=' + str(file_cid)
    res = requests.post(url)
    #When the download finishes resetting the field
    if res.status_code == 200:
        file_downloaded = 2
        file_cid = ''
    else:
        file_downloaded = 0

def compute_peer_metrics(peer):
    '''
    Check if a peer is already known by the system and in that case check if that peer has sent more data, then compute the values.
    If the peer is already known and has not sent more data ignore it.
    '''
    global collaborating_peers
    #Variable that indicates if the peer is found in the already known peers
    found = False
    for p in collaborating_peers:
        #Updating the existing peer if it is an already known collaborating peer
        if (peer['Peer'] == p['Peer']):
            if peer['Exchanged'] > p['Exchanged']:
                p['Bytes_received'] = peer['Bytes_received']
                p['Bytes_sent'] = peer['Bytes_sent']
                p['Exchanged'] = peer['Exchanged']
            found = True
            break
    #If the peer is not in the actual collaborating peers, searching it in the previously known peers
    if found == False:
        for p in known_peers:
            #If something has changed in known peers means that the peer has sent more data, in that case adding it to the collaborating peers
            if (peer['Peer'] == p['Peer']):
                if peer['Exchanged'] > p['Exchanged']:
                    #Getting the country of the IPv4 address of the peer
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
    #If it is the first time that we encounter the peer, adding it to the collaborating peers
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
    global peers_number
    global bw
    #Resetting known peers
    known_peers = []
    #Resetting collaborating peers
    collaborating_peers = []
    #Resetting number of peers
    peers_number = {
        'n_peers':[],
        'times':[],
        'c_peers':[]
    }
    #Resetting bandwidth
    bw = {
        'actual_in':[],
        'avg_in':[],
        'times':[]
    }
    #Sending an ipfs bitswap stat to know the bitswap partners
    res =  requests.post('http://127.0.0.1:5001/api/v0/bitswap/stat')
    peers = res.json()['Peers']
    for peer in peers:
        #Querying the bitswap agent ledger for peer information
        string = 'http://127.0.0.1:5001/api/v0/bitswap/ledger?arg='+str(peer)
        restmp = requests.post(string)
        peer_infos = restmp.json()
        #If the peer has no data exchanged, ignoring it, else saving its state
        if (peer_infos['Exchanged'] > 0):
            known_peers.append({
                'Peer':peer_infos['Peer'],
                'Bytes_sent':peer_infos['Sent'],
                'Bytes_received':peer_infos['Recv'],
                'Value':peer_infos['Value'],
                'Exchanged':peer_infos['Exchanged']
            })
    #Printing the list of the peer known at the start of the download
    print('Known peers:')
    for elem in known_peers:
        print(elem)

def check_collaborating_peers():
    '''
    Check the peers who are collaborating with my node to download of this precise file
    '''
    global peers_number
    #Getting all the partners, sending an ipfs bitswap stat request
    res =  requests.post('http://127.0.0.1:5001/api/v0/bitswap/stat')
    peers = res.json()['Peers']
    
    #Getting the number of total peers associated to a timestamp
    peers_number['n_peers'].append(len(peers))
    now = datetime.datetime.now()
    date_str = ''
    minute = 0
    hour = 0
    second = 0
    if now.hour < 10:
        hour = '0' + str(now.hour)
    else:
        hour = str(now.hour)
    if now.minute < 10:
        minute = '0' + str(now.minute)
    else:
        minute = str(now.minute)
    if now.second < 10:
        second = '0' + str(now.second)
    else:
        second = str(now.second)
    date_str = hour + ':' + minute + ':' + second
    peers_number['times'].append(date_str)

    for peer in peers:
        #Query the bitswap agent for the ledger for peer information
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
            #Making all the checks and eventually update the collaborating peers
            compute_peer_metrics(info)
    #Getting also the number of collaborating peers
    peers_number['c_peers'].append(len(collaborating_peers))
    #Print the information about the peers that are collaborating
    print('Collaborating peers:')
    for elem in collaborating_peers:
        print(elem)

def clean_ip_addresses(ips):
    '''
    Filters a peer's addresses and keep only the public IPv4 address
    '''
    ip_addrs = []
    for ip in ips:
        ip_parts = ip.split('/')
        ip_type = ip_parts[1]
        #Considering only the IPv4 address
        if ip_type == 'ip4':
            ip_addr = ip.split('/')[2]
            #Not considering private addresses
            if(ip_addr[0:9] != '127.0.0.1' and ip_addr[0:7] != '192.168' and ip_addr[0:2] != '10' and ip_addr[0:6] != '172.31'):
                #Add the address only it is not already present (due to the association address/port)
                if (ip_addr) not in ip_addrs:
                    ip_addrs.append(ip_addr)
    return ip_addrs

def get_bandwidth():
    '''
    Save the actual bandwidth value and compute the average bandwidth
    '''
    global bw
    #Sending an ipfs stats bw query
    url = 'http://127.0.0.1:5001/api/v0/stats/bw'
    res = requests.post(url)
    r = res.json()
    #Getting the timestamp
    now = datetime.datetime.now()
    rate_in = r['RateIn']
    bw['actual_in'].append(rate_in)
    date_str = ''
    minute = 0
    hour = 0
    second = 0
    if now.hour < 10:
        hour = '0' + str(now.hour)
    else:
        hour = str(now.hour)
    if now.minute < 10:
        minute = '0' + str(now.minute)
    else:
        minute = str(now.minute)
    if now.second < 10:
        second = '0' + str(now.second)
    else:
        second = str(now.second)
    date_str = hour + ':' + minute + ':' + second
    #Adding an entry for these values in the data structure
    bw['times'].append(date_str)
    n_val = len(bw['avg_in'])
    if n_val == 0:
        new_avg = rate_in
    else:
        new_avg = ((bw['avg_in'][n_val - 1] * n_val) + rate_in) / (n_val + 1)
    bw['avg_in'].append(new_avg)
    #Printing bandwidth information
    print('Actual incoming bandwidth: ' + str(rate_in))
    print('Average incoming bandwidth: ' + str(new_avg))
    print('Actual outcoming bandwidth: ' + str(r['RateOut']))    

def who_is_peer(peer):
    '''
    Search the multiaddresses of a peer and his country
    '''
    #Sending an ipfs dht findpeer requests to know the addresses associated at this peerId
    url = 'http://127.0.0.1:5001/api/v0/dht/findpeer?arg='+str(peer)
    restmp = requests.post(url)
    results = restmp.json(cls=ndjson.Decoder)
    for result in results:
        #Parsing the result
        responses = result["Responses"]
        if responses is not None:
            for res in responses:
                #Getting only the addresses
                addrs = res['Addrs']
                #Filtering the addresses to get only the public IPv4 address
                ip_addrs = clean_ip_addresses(addrs)
                if len(ip_addrs) == 1:
                    ip = ip_addrs[0]
                    #Searching the country for this address
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
                        #If the acronym is (XX) the country is unknown so the system ignores it
                        return ('Unknown Country', ip)
    return (None, None)

def create_plot():
    '''
    Create the plots and return the json of them
    '''
    #Updating the list of collaborating peers
    check_collaborating_peers()
    
    #Creating plots for bytes received and exchanged blocks
    peer_ids = []
    bytes_received = []
    exchanged_blocks = []
    peers = collaborating_peers
    #For every collaborating peer taking the information
    for p in peers:
        peer_ids.append(p['Peer'])
        bytes_received.append(p['Bytes_received'])
        exchanged_blocks.append(p['Exchanged'])
    #Creating a dict in the format requested to create a dataframe
    data_dict = dict()
    data_dict = {
        'Peer_ids':peer_ids,
        'Bytes_received':bytes_received,
        'Exchanged_blocks':exchanged_blocks
    }
    #Creating the dataframe requested from Plotly to create the plots
    df = pd.DataFrame.from_dict(data_dict)
    #Building the plots
    bytes_received = go.Bar(
        x = df['Peer_ids'],
        y = df['Bytes_received'],
        name = 'Bytes received',
        marker = dict(color = 'rgba(255, 174, 255, 0.5)', line=dict(color='rgb(0,0,0)',width=1.5))
    )
    exchanges = go.Bar(
        x = df['Peer_ids'],
        y = df['Exchanged_blocks'],
        name = 'Exchanged blocks',
        marker = dict(color = 'rgba(255, 255, 128, 0.5)', line=dict(color='rgb(0,0,0)',width=1.5))
    )

    #Creating a map with the IP addresses location
    countries = dict()
    #Counting peers for each country
    for peer in peers:
        country = peer['Country']
        #Ignoring the peer for which the country is unknown
        if country is not None and country != 'Unknown Country':
            if country in countries:
                countries[country] = countries[country] + 1
            else:
                countries[country] = 1
    cs = []
    ps = []
    #Creating a dict with the information in the format requested to create a dataframe
    for country in countries:
        cs.append(country)
        ps.append(countries[country])
    dfmap = pd.DataFrame.from_dict(dict(Countries=cs, Peers=ps))
    #Printing the dataframe and building a bubble map with the dataframe
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
            colorscale = 'blugrn',
            cmin = 0,
            color = dfmap['Peers'],
            cmax = dfmap['Peers'].max(),
            colorbar_title="Number of peers"
        )
    )

    #Creating the bandwidth plot
    get_bandwidth()
    df = pd.DataFrame.from_dict(bw)
    #Line for actual bandwidth
    bw_peers = go.Scatter(
        y = df['actual_in'],
        x = df['times'],
        name = "Actual incoming bandwidth"
    )
    #Line for average bandwidth
    avg_bw_peers = go.Scatter(
        y = df['avg_in'],
        x = df['times'],
        name = "Average incoming bandwidth"
    )

    #Creating a plot for the number of bitswap partners (total and collaborating)
    df = pd.DataFrame.from_dict(peers_number)
    #Line for total partners
    n_peers = go.Scatter(
        x = df['times'],
        y = df['n_peers'],
        name = "Total peers"
    )
    #Line for collaborating partners
    c_peers = go.Scatter(
        x = df['times'],
        y = df['c_peers'],
        name = "Collaborating peers"
    )

    #Creating json of the plots
    data1 = [bytes_received]
    data1j = json.dumps(data1, cls=plotly.utils.PlotlyJSONEncoder)
    data2 = [exchanges]
    data2j = json.dumps(data2, cls=plotly.utils.PlotlyJSONEncoder)
    data3 = [maps]
    data3j = json.dumps(data3, cls=plotly.utils.PlotlyJSONEncoder)
    data4 = [n_peers, c_peers]
    data4j = json.dumps(data4, cls=plotly.utils.PlotlyJSONEncoder)
    data5 = [bw_peers, avg_bw_peers]
    data5j = json.dumps(data5, cls=plotly.utils.PlotlyJSONEncoder)
    array = [data1j, data2j, data3j, data4j, data5j]
    return array

@app.route('/', methods=['GET','POST'])
def index():
    '''
    Index function
    '''
    global file_downloaded
    global file_cid
    form = DownloadForm()
    #In the case that a download is already started returning the page that shows the graphs
    if file_downloaded != 0:
        return render_template('plot.html', file_cid=file_cid)
    #If the request is a POST an user requests a download
    if request.method == 'POST':
        if form.validate_on_submit():
            #Getting the CID of the content from the form
            file_cid = request.form['file_cid']
            #Starting file download in another thread to not wait for the response
            thread = threading.Thread(target=get_file,args=(file_cid,))
            thread.start()
            #Returning the page that shows the graphs
            return render_template('plot.html', file_cid=file_cid)
    else:
        #If the request is a GET returning the index page
        file_downloaded = 0
        return render_template('index.html', form=form)

@app.route('/plots')
def update_plot():
    '''
    Updates the plots and return them in json format
    '''
    plots = create_plot()
    return json.dumps(plots)

@app.route('/file')
def file_info():
    '''
    Communicates the state of the file's download
    '''
    return json.dumps(file_downloaded)

if __name__ == '__main__':
    app.run()

    