import requests
import threading
import time

def get_file(file_cid):
    print("Trying to download "+file_cid )
    url = 'http://127.0.0.1:5001/api/v0/get?arg=' + str(file_cid) + '&output=./'
    res = requests.post(url)
    print(res)

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

def check_collaborating_peers(known_peers):
    '''
    Check the peers who are collaborating with my node to download the file
    '''
    res =  requests.post('http://127.0.0.1:5001/api/v0/bitswap/stat')
    peers = res.json()['Peers']
    collaborating_peers = []
    for peer in peers:
        #Query the bitswap agent for the ledger for peer informations
        string = 'http://127.0.0.1:5001/api/v0/bitswap/ledger?arg='+str(peer)
        restmp = requests.post(string)
        peer_infos = restmp.json()
        #If the peer has no data exchanged, ignore it, else add it to the collaborating peers
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
    print('Collaborating peers:')
    for elem in collaborating_peers:
        print(elem)
    return collaborating_peers

def main():
    #Get known peers
    known_peers = check_known_peers()
    #file_cid = "QmbsZEvJE8EU51HCUHQg2aem9JNFmFHdva3tGVYutdCXHp"
    #file_cid = 'QmQ2r6iMNpky5f1m4cnm3Yqw8VSvjuKpTcK1X7dBR1LkJF'
    file_cid = 'QmSnuWmxptJZdLJpKRarxBMS2Ju2oANVrgbr2xWbie9b2D'
    #file_cid = 'QmNoscE3kNc83dM5rZNUC5UDXChiTdDcgf16RVtFCRWYuU'
    #Start the thread that gets the file
    t = threading.Thread(target=get_file,args=(file_cid,))
    t.start()
    while (t.is_alive()):
        collaborating_peers = check_collaborating_peers(known_peers)
        #Wait 5 seconds
        time.sleep(5)

if __name__ == '__main__':
    main()