# UofMBlockchainPeer

Run with python3 blockchain_peer.py PORT

I have included a mining function that runs for self.MINE_INTERVAL time in the program main loop.
Since the mining occurs in program main loop, it is not responsive to requests when mining.
To simply run as a peer without mining, set self.MINE_INTERVAL to 0. (it is currently 0).
To mine, set self.MINE_INTERVAL to how long you want to mine for.
When mining, set self.SERVE_INTERVAL for how long you want to serve between mining sessions.

Explainations:

Cleaning up peers is performed in the update_peers method.
This method is repeatedly called in the programs main loop.
In the methods, the current time is checked against the last time the peer has been heard from.
If time.time() - last_ping > 60, then that peers has not flooded in at elastt 60 seconds, and they are dropped.

The chain is verified in the method verify_blockchain.
For each block, the hash contained in it is compared against the expected calculated hash for the block.
Verification is passed if all blocks succeed, and fails if any block does not have correct hash.


Obtaining consensus chain:
First send stats to peers in get_stats. This method ensures we receive at least 1 stat.
Consensus chain is chosen in method get_consensus_stat(stats).
	First the longest chain is selected. This ensures we never move to a shorter chain.
	If there are multiple longest chains, then chain with majority wins.
	Majority is determined by how many addresses sent that particular height and hash.
Get the addrs who hold the consensus stat with get_addrs_w_consensus_stat()
Then load consensus chain using load_chain(consensus_stat, addrs_w_consensus_stat) method.
This process ensures we collect and load current consensus chain whenever prompted.





