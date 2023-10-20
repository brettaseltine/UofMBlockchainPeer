import random
import socket
import sys
import uuid
import json
import time
import hashlib

class BlockchainPeer:

    def __init__(self):
        self.WELL_KNOWN_HOST = 'silicon.cs.umanitoba.ca'
        self.WELL_KNOWN_PORT = 8999
        self.MY_PORT = int(sys.argv[1])
        self.TIMEOUT_TIME = 1
        self.NAME = 'berttt'
        self.my_peers = Peers()
        self.last_flood_time = 0
        self.last_sent_consensus_req_time = 0;
        self.REFRESH_TIME = 30
        self.DROP_PEER_TIME = 60
        self.MAX_PEERS = 20
        self.blockchain = []        # list of Block objects
        self.DIFFICULTY = 8

        self.mine_messages = ['wordzz', 'hello']
        self.MINE_INTERVAL = 0
        self.SERVE_INTERVAL = 100

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind( (socket.gethostname(), self.MY_PORT) )
        self.sock.settimeout(self.TIMEOUT_TIME)

    #------------------------------------------------------------------------------
    # JOINING NETWORK METHODS
    #------------------------------------------------------------------------------
    def send_flood(self):
        print('Sending flood...')
        try:
                flood_msg = {
                    'type': 'FLOOD',
                    'host': self.sock.getsockname()[0],
                    'port': int(self.sock.getsockname()[1]),
                    'id': str(uuid.uuid4()),
                    'name': self.NAME
                }
                print('host: {}, port, {}'.format(self.sock.getsockname()[0], int(self.sock.getsockname()[1])) )
                self.sock.sendto(json.dumps(flood_msg).encode(), (self.WELL_KNOWN_HOST, self.WELL_KNOWN_PORT))
                self.last_flood_time = time.time()
                print('Successfully sent flood!')
                return True
        except:
            print('Failed to send flood')
            return False

    def recv_floods(self):
        '''Add flooders to peer list. Run for specified time'''

        start_time = time.time()
        while time.time() < start_time + self.TIMEOUT_TIME:
            try:
                data, addr = self.sock.recvfrom(2048)
                msg = json.loads(data.decode())
                if msg['type'] == 'FLOOD_REPLY':
                    self.process_flood_reply_msg(msg)
                if msg['type'] == 'FLOOD':
                    self.process_flood_msg(msg)
            except:
                pass

    def process_flood_reply_msg(self, msg):
        try:
            print('Received FLOOD_REPLY from {}'.format(msg['name']))
            new_p = Peer(msg['host'], msg['port'], msg['name'], time.time())
            self.my_peers.add(new_p)
        except KeyError as e:
            print('invalid FLOOD_REPLY msg!, will ignore')
            return

    def process_flood_msg(self, flood_msg):
        # add peer to list
        try:
            print('Received FLOOD from {}'.format(flood_msg['name']))
            new_p = Peer(flood_msg['host'], flood_msg['port'], flood_msg['name'], time.time())
            if self.my_peers.contains(new_p):
                self.my_peers.get(new_p).update_last_ping()
            else:
                self.my_peers.add(new_p)
        except KeyError as e:
            print('invalid FLOOD msg! will ignore')
            return
        # send reply
        try:
            flood_reply = {
                'type': 'FLOOD_REPLY',
                'host': self.sock.getsockname()[0],
                'port': int(self.sock.getsockname()[1]),
                'name': self.NAME
            }
            self.sock.sendto(json.dumps(flood_reply).encode(), (flood_msg['host'], flood_msg['port']) )
            print( 'Sent FLOOD_REPLY to {}'.format(flood_msg['name']) )
        except:
            print('failed to send FLOOD_REPLY')
    
    #------------------------------------------------------------------------------
    # OBTAIN VALID BLOCKCHAIN
    #------------------------------------------------------------------------------
    def get_valid_blockchain(self):
        print('\nGETTING VALID BLOCKCHAIN\n')
        result = False
        while not result:
            stats = self.get_stats()
            cs = self.get_consensus_stat(stats)
            cs_addrs = self.get_addrs_w_consensus_stat(cs, stats)
            self.load_blockchain(cs, cs_addrs)
            result = self.verify_blockchain()
        print('\n\nOBTAINED VALID BLOCKCHAIN\n')

    #------------------------------------------------------------------------------
    # GET CONSENSUS CHAIN METHODS
    #------------------------------------------------------------------------------
    def get_addrs_w_consensus_stat(self, consensus_stat, stats):
        desired_addrs = []
        for stat in stats:
            if stat.height == consensus_stat.height and stat.hash == consensus_stat.hash:
                desired_addrs.append(stat.holding_addr)
        
        return desired_addrs
    
    def get_consensus_stat(self, stats):
        if len(stats) == 0: return None
        
        # find stat with largest height
        longest_list = [stats[0]]
        best = stats[0]
        for stat in stats:
            if stat.height > best.height:
                best = stat
                longest_list = [stat]
            elif stat.height == best.height:
                longest_list.append(stat)
            
        # if have multiple of same length, must choose most agreed upon
        if len(longest_list) > 1:
            # count occurence of each hash
            counts = {}
            for stat in longest_list:
                if stat.hash in counts:
                    counts[stat.hash] += 1
                else:
                    counts[stat.hash] = 1
            # select most counted
            highest_count = max( counts.values() )
            for c in counts:
                if counts[c] == highest_count:
                    for stat in stats:
                        if stat.hash == c:
                            best = stat
        print('Consensus blockchain has height {} and hash {}\n'.format(best.height, str(best.hash)) )
        return best

    def get_stats(self):
        from_peers = self.my_peers.copy()

        # send stats request to get chain info from peers, send again to non-responders
        # (it is possible a peer is faulty and will never respond, thus we will move on after 2 ignored requests)
        print('Requesting stats from peers')
        stats = self.request_stats(from_peers)
        stats += self.request_stats(from_peers)
        # we cannot continue until at least 1 stat is received
        while len(stats) == 0:
            stats += self.request_stats(from_peers)
        
        print('\n\nGot these stats:\n', stats, '\n\n')
        return stats

    def request_stats(self, from_peers):
        '''
        Warning: from_peers is modified.
        Obtains stats from peers, then removes peer from list
        '''
        stats = []

        # send request
        for i in range(from_peers.count()):
            from_peer = from_peers.get_at_pos(i)
            self.send_for_stat(from_peer)
        
        # obtain response
        start_time = time.time()
        while(time.time() < start_time + self.TIMEOUT_TIME):
            stat = self.recv_stat()
            if stat:
                stats.append(stat)
                # remove peer who responded
                from_peers.remove_peer_w_addr(stat.holding_addr)
        
        return stats

    def send_for_stat(self, peer):
        try:
            print('Sending stats request to', peer.host, peer.port)
            stats_req = {'type': 'STATS'}
            self.sock.sendto(json.dumps(stats_req).encode(), (peer.host, peer.port) )
        except:
            print('Send for stats failed')

    def recv_stat(self):
        try:
            data, addr = self.sock.recvfrom(2048)
            msg = json.loads(data.decode())
            if msg['type'] == 'STATS_REPLY':
                print('Received STATS_REPLY from', addr)
                the_stat =  Stat(msg['height'], msg['hash'], addr)
                if the_stat.is_fully_initialized():
                    return the_stat
        except:
            pass
        return None

    #------------------------------------------------------------------------------
    # BUILD BLOCKCHAIN METHODS
    #------------------------------------------------------------------------------

    def load_blockchain(self, consensus_stat, addrs_w_cons_stat):
        self.blockchain.clear()
        pending_block_heights = list( range(0, consensus_stat.height) )
        
        while len(pending_block_heights) > 0:
            # send
            print('\nSending GET_BLOCK for {} remaining blocks'.format(len(pending_block_heights)))
            for height in pending_block_heights:
                to_addr = random.choice(addrs_w_cons_stat)
                self.send_get_block(height, to_addr)
            # receive
            start_time = time.time()
            while time.time() < start_time + self.TIMEOUT_TIME:
                block = self.get_block_reply()
                if block != None:
                    # ensure block not already added
                    for b in self.blockchain:
                        if b.height == block.height:
                            break

                    print('Adding block', block.height)
                    self.blockchain.append(block)
                    pending_block_heights.remove(block.height)
            # remaining tasks
            self.keep_alive()
            
        # sort blockchain by block height
        self.blockchain.sort(key=lambda block: block.height)

        print('\nLOADED BLOCKCHAIN')

    def send_get_block(self, height, to_addr):
        try:
            get_block = {
                'type': 'GET_BLOCK',
                'height': height
            }
            self.sock.sendto(json.dumps(get_block).encode(), to_addr )
        except:
            print('Send GET_BLOCK failed')

    def get_block_reply(self):
        try:
            data, addr = self.sock.recvfrom(2048)
            msg = json.loads(data.decode())
            if msg['type'] == 'GET_BLOCK_REPLY':
                print('Received block {}'.format(msg['height']))
                block = Block(msg)
                if block.is_fully_initialized():
                    return block
        except:
            pass
        return None

    def add_block(self, block):
        # verify block
        result = self.verify_block(block)
        if result:
            print('\n\nSUCCESSFULLY ADDED BLOCK TO BLOCKCHAIN\n\n')
            self.blockchain.append(block)
        else:
            print('BLOCK VERIFICATION FAILED, WILL NOT ADD TO CHAIN')

    #------------------------------------------------------------------------------
    # VERIFY CHAIN METHODS
    #------------------------------------------------------------------------------
    def verify_blockchain(self):
        print('\nVERIFYING BLOCKCHAIN')
        hash = None
        for block in self.blockchain:
            hash = self.hash_block(block, hash)
            if hash is None:
                print('Failed verification')
                return False
            if hash != block.hash:
                print('Wrong hash, verification failed!')
                print('block {} has wrong hash'.format(block.height))
                print('calculated', hash)
                print('expected', block.hash)
                return False
        print('Blockchain verification successful!')
        return True

    def verify_block(self, block):
        calculated_hash = self.hash_block(block, self.prev_block_hash(block))
        return True if calculated_hash == block.hash else False

    def hash_block(self, block, prev_hash):
        print('hashing block', block.height)
        hash_base = hashlib.sha256()
        # add it to this hash
        if prev_hash:
            hash_base.update(prev_hash.encode())
        # add the miner
        hash_base.update(block.mined_by.encode())
        # add the messages in order
        for m in block.messages:
            hash_base.update(m.encode())
        # add timestamp as 64 bit byte string
        hash_base.update(block.timestamp.to_bytes(8, 'big'))
        # add nonce
        hash_base.update(block.nonce.encode())
        # get hex
        hash = hash_base.hexdigest()
        # verify difficulty
        if hash[-1 * self.DIFFICULTY:] != '0' * self.DIFFICULTY:
            print('Block was not difficult enough: {}'.format(hash))
            return None
        else:
            print('Block {} hashed'.format(block.height))
        return hash
    
    def prev_block_hash(self, cur_block):
        count = 0
        for block in self.blockchain:
            if block == cur_block:
                break
            count += 1
        prev_at = count - 1
        return self.blockchain[prev_at].hash if prev_at >= 0 else None

    def perform_consensus(self):
        try:
            print('\nPERFORMING CONSENSUS\n')
            stats = self.get_stats()
            cs = self.get_consensus_stat(stats)
            print('consensus height', cs.height, 'my height', self.blockchain[-1].height+1)
            print('consensus hash', cs.hash, 'my hash', self.blockchain[-1].height+1)
            if cs.height == self.blockchain[-1].height+1 and cs.hash == self.blockchain[-1].hash:
                print('\nCONSENSUS PASSED\n')
            else:
                print('\nCONSENSUS FAILED, will request current chain')
                self.get_valid_blockchain()
        except:
            print('\nCONSENSUS FAILED, will request current chain')
            self.get_valid_blockchain()

    #------------------------------------------------------------------------------
    # MINING METHODS
    #------------------------------------------------------------------------------

    def process_new_word(self, msg):
        try:
            print('Adding new word to mine_messages')
            if len(self.mine_messages) < 10:
                self.mine_messages.append(msg['word'])
            else:
                self.mine_messages[random.randint(0,9)] = msg
        except KeyError as e:
            print('Invalid NEW_WORD format')
    
    def mine(self, end_time):
        hash = '111111111111111111111111111'
        last_block_hash = self.hash_block(self.blockchain[-1], self.prev_block_hash(self.blockchain[-1]))
        while hash[-1 * self.DIFFICULTY:] != '0' * self.DIFFICULTY and time.time() < end_time:
            hash_base = hashlib.sha256()
            hash_base.update(last_block_hash.encode())
            hash_base.update(self.NAME.encode())
            for m in self.mine_messages:
                hash_base.update(m.encode())
            timestamp = int(time.time())
            hash_base.update(timestamp.to_bytes(8, 'big'))
            nonce = uuid.uuid4().hex
            hash_base.update(nonce.encode())
            hash = hash_base.hexdigest()
        
        if hash[-1 * self.DIFFICULTY:] == '0' * self.DIFFICULTY:
            print('FOUND HASH, WILL ANNOUNCE BLOCK')
            print(hash)
            announce_msg = {
                'type': 'ANNOUNCE',
                'height': len(self.blockchain),
                'minedBy': self.NAME,
                'nonce': str(nonce),
                'messages': self.mine_messages,
                'timestamp': timestamp,
                'hash': hash
            }
            for i in range(self.my_peers.count()):
                peer = self.my_peers.get_at_pos(i)
                self.sock.sendto(json.dumps(announce_msg).encode(), (peer.host, peer.port))
            print('BLOCK HAS BEEN ANNOUNCED')

    #------------------------------------------------------------------------------
    # RUNNING AS PEER METHODS
    #------------------------------------------------------------------------------
    def do_running_tasks(self):
        self.keep_alive()
        self.update_peers()
        self.manage_sending_consensus()

    def keep_alive(self):
        if time.time() - self.last_flood_time > self.REFRESH_TIME:
            self.send_flood()

    def update_peers(self):
        for i in range(self.my_peers.count()):
            peer = self.my_peers.get_at_pos(i)
            if time.time() - peer.last_ping > self.DROP_PEER_TIME:
                print('Dropping ', peer.name)
                self.my_peers.remove(peer)
                break;

    def manage_sending_consensus(self):
        if time.time() - self.last_sent_consensus_req_time > (5 * 60):
            self.request_consensus_from_peers()

    def process_stats_msg(self, addr):
        try:
            print('Received STATS from {}'.format(addr))
            stats_reply = {
                'type': 'STATS_REPLY',
                'height': len(self.blockchain),
                'hash': self.blockchain[-1].hash
            }
            self.sock.sendto(json.dumps(stats_reply).encode(), addr)
            print( 'Sent STATS_REPLY to {}'.format(addr))
        except Exception as e:
            print('failed to send STATS_REPLY')

    def process_announce_msg(self, msg):
        try:
            print('Received ANNOUNCE')
            new_block = Block(msg)
            self.add_block(new_block)
        except KeyError as e:
            print('Block invalid, will ignore')

    def process_get_block(self, msg, to_addr):
        try:
            print('Received GET_BLOCK', msg['height'])
            the_block = self.blockchain[msg['height']]
            block_dict = the_block.to_dict()
            block_dict['type'] = 'GET_BLOCK_REPLY'
            self.sock.sendto(json.dumps(block_dict).encode(), to_addr)
            print('SEND GET_BLOCK_REPLY to {}'.format(to_addr))
        except IndexError as e:
            print('Do not have block {}. Will return block with null vals'.format(msg['height']))
            msg = {
                'hash': 'null',
                'height': 'null',
                'messages': 'null',
                'minedBy': 'null',
                'nonce': 'null',
                'timestamp': 'null'
            }
            self.sock.sendto(json.dumps(msg).encode(), to_addr)
        except:
            print('Failed to reply to GET_BLOCK')

    def request_consensus_from_peers(self):
        try:
            print('\nPROMPTING PEERS TO PERFORM CONSENSUS\n')
            msg = {'type': 'CONSENSUS'}
            formatted_msg = json.dumps(msg).encode()
            for i in range(self.my_peers.count()):
                peer = self.my_peers.get_at_pos(i)
                self.sock.sendto( formatted_msg, (peer.host, peer.port) )
            print('Consensus request sent successfully!')
            self.last_sent_consensus_req_time = time.time()
        except:
            print('Failed to send consensus request')


    #------------------------------------------------------------------------------
    # DRIVER METHODS
    #------------------------------------------------------------------------------
    def setup(self):
        # join network
        self.send_flood()
        self.recv_floods()
        print('\n\nTHESE ARE MY PEERS\n{}\n\n'.format(self.my_peers))

        self.get_valid_blockchain()
    
    def run_peer(self):
        try:
            self.setup()
            while True:
                print('RUNNING AS FULL PEER')
                self.do_running_tasks()
                start_time = time.time()
                while time.time() < start_time + self.SERVE_INTERVAL:
                    try:
                        # receive message
                        data, addr = self.sock.recvfrom(2048)
                        print('received: {} from: {}'.format(data.decode(), addr))

                        # process message
                        msg = json.loads(data.decode())
                        if msg['type'] == 'FLOOD':
                            self.process_flood_msg(msg)
                        elif msg['type'] == 'FLOOD_REPLY':
                            self.process_flood_reply_msg(msg)
                        elif msg['type'] == 'STATS':
                            self.process_stats_msg(addr)
                        elif msg['type'] == 'ANNOUNCE':
                            self.process_announce_msg(msg)
                        elif msg['type'] == 'CONSENSUS':
                            self.perform_consensus()
                        elif msg['type'] == 'NEW_WORD':
                            self.process_new_word(msg)
                        elif msg['type'] == 'GET_BLOCK':
                            self.process_get_block(msg, addr)
                    
                    except json.JSONDecodeError as e:
                        print('invalid msg! not JSON format, will ignore msg')
                    except KeyError and TypeError as e:
                        print('invalid msg!, invalid type, will ignore msg')
                    except socket.timeout as e:
                        pass

                self.do_running_tasks()
                
                if self.MINE_INTERVAL > 0:
                    print('\nMINING for {} seconds\n'.format(self.MINE_INTERVAL))
                    self.mine(time.time() + self.MINE_INTERVAL)

        except KeyboardInterrupt as e:
            print('\nBye!')
            self.sock.close()
            sys.exit(0)
        except Exception as e:
            print('Unexpected error... quitting')
            print(e)
            sys.exit()

class Peer:
    def __init__(self, host, port, name, last_ping):
        self.host = host
        self.port = port
        self.name = name
        self.last_ping = last_ping

    def copy(self):
        return Peer(self.host, self.port, self.name, self.last_ping)

    def is_fully_initialized(self):
        try:
            if self.host != None and self.port != None and self.name != None and self.last_ping != None:
                return True
            return False
        except:
            return False
    
    def is_equal(self, other_peer):
        if other_peer is None: return False
        if (self.host == other_peer.host and
            self.port == other_peer.port and
            self.name == other_peer.name):
            return True
        return False

    def update_last_ping(self):
        self.last_ping = time.time()
    
    def __repr__(self):
        return self.name

class Peers:
    def __init__(self):
        self.peer_list = []

    def add(self, new_peer):
        ''' Elements are only added if unique and not me, ignored otherwise. Basically a Set add'''
        for peer in self.peer_list:
            if (not peer.is_fully_initialized()) or peer.is_equal(new_peer):
                return False
            if peer.host == socket.gethostbyname(socket.gethostname()) and peer.port == int(sys.argv[1]):
                # wont add me as peer
                return False
        self.peer_list.append(new_peer)
        return True
    
    def remove(self, peer):
        if peer in self.peer_list:
            self.peer_list.remove(peer)
    
    def remove_peer_w_addr(self, addr):
        for p in self.peer_list:
            if p.host == addr[0] and p.port == addr[1]:
                self.remove(p)

    def get(self, peer):
        for p in self.peer_list:
            if p.is_equal(peer):
                return p
        return None

    def get_at_pos(self, i):
        return self.peer_list[i]

    def count(self):
        return len(self.peer_list)

    def copy(self):
        new_peers = Peers()
        for p in self.peer_list:
            new_peers.add(p)
        return new_peers

    def contains(self, peer):
        for p in self.peer_list:
            if p.is_equal(peer):
                return True
        return False

    def __str__(self):
        s = ''
        for p in self.peer_list:
            s += str(p) + '\n'
        return s

class Stat:
    def __init__(self, height, hash, holding_addr):
        self.height = height
        self.hash = hash
        self.holding_addr = holding_addr

    def is_fully_initialized(self):
        try:
            if self.height != None and self.hash != None and self.holding_addr != None:
                return True
            return False
        except:
            return False

    def __repr__(self):
        return 'height: {}, hash: {}, from: {}'.format(self.height, self.hash, self.holding_addr)

class Block:
    def __init__(self, contents:dict):
        self.hash = contents['hash']
        self.height = contents['height']
        self.messages = contents['messages']
        self.mined_by = contents['minedBy']
        self.nonce = contents['nonce']
        self.timestamp = contents['timestamp']
    
    def is_fully_initialized(self):
        try:
            if (self.hash != None and self.height != None and self.messages != None and
                self.mined_by != None and self.nonce != None and self.timestamp != None):
                return True
            return False
        except:
            return False

    def to_dict(self):
        dict = {
            'hash': self.hash,
            'height': self.height,
            'messages': self.messages,
            'minedBy': self.mined_by,
            'nonce': self.nonce,
            'timestamp': self.timestamp
        }
        return dict

# run as peer
bp = BlockchainPeer()
bp.run_peer()


    