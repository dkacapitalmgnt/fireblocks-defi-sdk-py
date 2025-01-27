import logging
import time

from fireblocks_sdk.api_types import TRANSACTION_STATUS_CONFIRMING

from fireblocks_sdk import (
    FireblocksSDK,
    TransferPeerPath,
    DestinationTransferPeerPath,
    ONE_TIME_ADDRESS,
    VAULT_ACCOUNT,
    EXTERNAL_WALLET,
    TRANSACTION_STATUS_BLOCKED,
    TRANSACTION_STATUS_COMPLETED,
    TRANSACTION_STATUS_FAILED,
    TRANSACTION_STATUS_BROADCASTING,
)
from fireblocks_sdk.api_types import TRANSACTION_STATUS_CANCELLED
from .chain import Chain
from web3 import Web3

SUBMIT_TIMEOUT = 180
STATUS_KEY = "status"

FAILED_STATUS = [
    TRANSACTION_STATUS_FAILED,
    TRANSACTION_STATUS_BLOCKED,
    TRANSACTION_STATUS_CANCELLED,
]
PENDING_STATUS_TX_HASH = [
    TRANSACTION_STATUS_BROADCASTING,
    TRANSACTION_STATUS_CONFIRMING,
]


CHAIN_TO_ASSET_ID = {
    Chain.MAINNET: ("ETH", "https://cloudflare-eth.com"),
    Chain.ROPSTEN: (
        "ETH_TEST",
        "https://ropsten.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161",
    ),
    Chain.KOVAN: (
        "ETH_TEST2",
        "https://kovan.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161",
    ),
    Chain.GOERLI: (
        "ETH_TEST3",
        "https://goerli.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161",
    ),
    Chain.RINKEBY: (
        "ETH_TEST4",
        "https://rinkeby.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161",
    ),
    Chain.BSC: ("BNB_BSC", "https://bsc-dataseed.binance.org"),
    Chain.BSC_TEST: ("BNB_TEST", "https://data-seed-prebsc-1-s1.binance.org:8545"),
    Chain.POLYGON: ("MATIC_POLYGON", "https://polygon-rpc.com"),
    Chain.POLYGON_TEST: ("MATIC_POLYGON_MUMBAI", "https://rpc-mumbai.maticvigil.com"),
    Chain.AVALANCHE: ("AVAX", "https://api.avax.network/ext/bc/C/rpc"),
    Chain.AVALANCHE_TEST: ("AVAXTEST", "https://api.avax-test.network/ext/bc/C/rpc"),
    Chain.MOONRIVER: ("MOVR_MOVR", "https://rpc.moonriver.moonbeam.network"),
    Chain.MOONBEAM: ("GLMR_GLMR", "https://rpc.api.moonbeam.network"),
    Chain.SONGBIRD: ("SGB", "https://songbird.towolabs.com/rpc"),
    Chain.ARBITRUM: ("ETH-AETH", "https://rpc.ankr.com/arbitrum"),
    Chain.ARBITRUM_RIN: ("ETH-AETH-RIN", "https://rinkeby.arbitrum.io/rpc"),
    Chain.FANTOM: ("FTM_FANTOM", "https://rpc.ftm.tools/"),
    Chain.RSK: ("RBTC", "https://public-node.rsk.co"),
    Chain.RSK_TEST: ("RBTC_TEST", "https://public-node.testnet.rsk.co"),
    Chain.CELO: ("CELO", "https://rpc.ankr.com/celo"),
    Chain.CELO_BAK: (
        "CELO_BAK",
        "https://baklava-blockscout.celo-testnet.org/api/eth-rpc",
    ),
    Chain.OPTIMISM: ("ETH-OPT", "https://rpc.ankr.com/optimism"),
    Chain.OPTIMISM_KOVAN: (
        "ETH-OPT_KOV",
        "https://optimism-kovan.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161",
    ),
    Chain.RONIN: ("RON", "https://api.roninchain.com/rpc"),
}


class Web3Bridge:
    def __init__(
        self,
        fb_api_client: FireblocksSDK,
        vault_account_id: str,
        chain: Chain,
    ):
        """
        :param fb_api_client: Fireblocks API client.
        :param vault_account_id: The source vault which address will sign messages.
        :param chain: Object of type Chain to represent what network to work with.
        :param external_wallet_address: The address of the interacted *contract*.
        :param wl_uuid: (Optional) If the contract is whitelisted, it can be sent through the co-responding UUID.
        """
        self.fb_api_client = fb_api_client
        self.source_vault_id = vault_account_id
        self.chain = chain
        self.asset: str = CHAIN_TO_ASSET_ID[self.chain][0]
        self.web_provider = Web3(Web3.HTTPProvider(CHAIN_TO_ASSET_ID[self.chain][1]))

    def check_whitelisting(self, target_address: str):
        whitelist_address = False
        destination = None
        whitelisted_addresses = self.fb_api_client.get_external_wallets()
        target = target_address.lower()

        for address in whitelisted_addresses:
            for token in address["assets"]:
                if token["address"].lower() == target:
                    logging.debug("found address on whitelist")
                    whitelist_address == True
                    if self.asset == token["id"]:
                        logging.debug(f"found correct asset for whitelisted address")
                        destination = TransferPeerPath(EXTERNAL_WALLET, address["id"])
                        return destination
        if not destination:
            if whitelist_address:
                raise ValueError(
                    f"Address is whitelisted but not correct asset, address: {target}, asset: {self.asset}"
                )
            else:
                raise ValueError(
                    f"Address not whitelisted, address: {target}, asset: {self.asset}"
                )

    def send_transaction(
        self, transaction: dict, note="", test=False, approval_tx=False
    ) -> dict:
        """
        Takes a ready transaction after being built (using web3 buildTransaction()) and transmits it to Fireblocks.
        :param transaction: A transaction object (dict) to submit to the blockchain.
        :param note: (Optional) A note to submit with the transaction.
        :return:
        """
        if not test:
            if not approval_tx:
                destination = self.check_whitelisting(transaction["to"])
            else:
                destination = self.check_whitelisting(approval_tx)
        else:
            destination = DestinationTransferPeerPath(
                ONE_TIME_ADDRESS, one_time_address={"address": transaction["to"]}
            )

        return self.fb_api_client.create_transaction(
            tx_type="CONTRACT_CALL",
            asset_id=self.asset,
            source=TransferPeerPath(VAULT_ACCOUNT, self.source_vault_id),
            amount=str(int(transaction["value"])),
            destination=destination,
            note=note,
            extra_parameters={"contractCallData": transaction["data"]},
        )

    def check_tx_is_sent(self, tx_id):
        try:
            current_status = self.fb_api_client.get_transaction_by_id(tx_id)
            if current_status[STATUS_KEY] in ():
                return current_status
            else:
                time.sleep(1)
        except:
            return {}

    def check_tx_status_chain(self, tx_hash: str):
        logging.info("Checking on-chain status")
        try:
            receipt = self.web_provider.eth.wait_for_transaction_receipt(
                tx_hash, timeout=240, poll_latency=1
            )
        except Exception as e:
            logging.info("Failed getting the receipt")
            raise e
        if receipt["status"] == 0:
            logging.info("Transaction failed on chain")
            return False
        else:
            time.sleep(10)
            return True

    def check_tx_is_completed(self, tx_id) -> dict:
        """
        This function waits for SUBMIT_TIMEOUT*4 (180 by default) seconds to retrieve status of the transaction sent to
        Fireblocks. Will stop upon completion / failure.
        :param tx_id: Transaction ID from FBKS.
        :return: Transaction last status after timeout / completion.
        """
        timeout = 0
        transaction_hash = False
        previous_status = False

        while True:
            try:
                current_status = self.fb_api_client.get_transaction_by_id(tx_id)
            except Exception as e:
                logging.info(f"Error while getting FB transaction status: {e}")
                time.sleep(3)
                timeout += 3
                continue
            timeout += 1

            # Logging if status has changed
            if current_status[STATUS_KEY] != previous_status:
                previous_status = current_status[STATUS_KEY]
                logging.info(f"Pending fireblocks: {previous_status}")

            # Transaction seemed to have failed
            # TODO: This assumes transaction is not sent, is there a case where it looks failed but is not
            if current_status[STATUS_KEY] in FAILED_STATUS:
                logging.error(f"Fireblocks failed transaction: {current_status}")
                return False

            # Fireblocks confirms that tx is finished
            if current_status[STATUS_KEY] == TRANSACTION_STATUS_COMPLETED:
                # We want to still confirm state from chain
                transaction_hash = current_status["txHash"]
                return self.check_tx_status_chain(transaction_hash)

            # timeout while not yet confirmed or failed
            if timeout > SUBMIT_TIMEOUT:
                # If we have tx hash, confirm from blockchain if accepted or failed
                if transaction_hash:
                    try:
                        if self.check_tx_status_chain(transaction_hash):
                            return True
                    except:
                        pass
                # Cancel tx, caller should resend
                logging.error(
                    "Timeout while waiting for Fireblocks to confirm transaction"
                )
                self.fb_api_client.cancel_transaction_by_id(tx_id)
                return False

            # See if fireblocks provides tx hash at this point
            if (
                current_status[STATUS_KEY] in PENDING_STATUS_TX_HASH
                and not transaction_hash
            ):
                if "txHash" in current_status:
                    transaction_hash = current_status["txHash"]

            # Follow the transaction hash on-chain
            if transaction_hash:
                try:
                    return self.check_tx_status_chain(transaction_hash)
                except:
                    # likely timed out, increase timeout
                    timeout += 120

            logging.debug(current_status)
            time.sleep(1)
