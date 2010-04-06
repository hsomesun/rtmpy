# Copyright The RTMPy Project.
# See LICENSE for details.

"""
RTMP handshake support.

RTMP handshaking is similar (at least conceptually to syn/ack) handshaking. We
extend this concept. Each 'packet' (syn or ack) consists of a payload of data
which is represented by L{Packet}. It is up to the negotiators (which
generate/decode the packets} to determine if the packets are valid.

@since: 0.1
"""

import sys
import time

from zope.interface import implements

from rtmpy import util, protocol
from rtmpy.protocol import interfaces


HANDSHAKE_LENGTH = 1536

RTMP_PROTOCOL_VERSION = 3
MAX_PROTOCOL_VERSION = 31


class HandshakeError(protocol.BaseError):
    """
    Generic class for handshaking related errors.
    """


class ProtocolVersionError(HandshakeError):
    """
    Base error class for RTMP protocol version errors.
    """


class ProtocolTooHigh(ProtocolVersionError):
    """
    Raised if a protocol version is greater than can the requested version.
    """


class ProtocolDegraded(ProtocolVersionError):
    """
    Raised when a protocol version is lower than expected. This is a request
    from the remote endpoint to use a lower protocol version.
    """


class VerificationError(HandshakeError):
    """
    Raised if the handshake verification failed.
    """


class Packet(object):
    """
    A handshake packet.

    @ivar first: The first 4 bytes of the packet, represented as an unsigned
        long.
    @type first: 32bit unsigned int.
    @ivar second: The second 4 bytes of the packet, represented as an unsigned
        long.
    @type second: 32bit unsigned int.
    @ivar payload: A blob of data which makes up the rest of the packet. This
        must be C{HANDSHAKE_LENGTH} - 8 bytes in length.
    @type payload: C{str}
    @ivar timestamp: Timestamp that this packet was created (in milliseconds).
    @type timestamp: C{int}
    """

    first = None
    second = None
    payload = None
    timestamp = None

    def __init__(self, **kwargs):
        timestamp = kwargs.get('timestamp', None)

        if not timestamp:
            kwargs['timestamp'] = int(time.time())

        self.__dict__.update(kwargs)

    def encode(self, buffer):
        """
        Encodes this packet to a stream.
        """
        buffer.write_ulong(self.first or 0)
        buffer.write_ulong(self.second or 0)

        buffer.write(self.payload)

    def decode(self, buffer):
        """
        Decodes this packet from a stream.
        """
        self.first = buffer.read_ulong()
        self.second = buffer.read_ulong()

        self.payload = buffer.read(HANDSHAKE_LENGTH - 8)


class BaseNegotiator(object):
    """
    Base functionality for negotiating an RTMP handshake.

    @ivar observer: An observer for handshake negotiations.
    @type observer: L{IHandshakeObserver}
    @ivar buffer: Any data that has not yet been consumed.
    @type buffer: L{util.BufferedByteStream}
    @ivar started: Determines whether negotiations have already begun.
    @type started: C{bool}
    @ivar protocolVersion: The handshake version that this negotiator
        understands.
    @ivar my_syn: The initial handshake packet that will be sent by this
        negotiator.
    @type my_syn: L{Packet}
    @ivar my_ack: The handshake packet that will be sent after the peer has sent
        its syn.
    @ivar peer_syn: The initial L{Packet} received from the peer.
    @ivar peer_ack: The L{Packet} received in acknowledgement of my syn.
    @ivar peer_version: The handshake version that the peer understands.
    """

    implements(interfaces.IHandshakeNegotiator)

    protocolVersion = RTMP_PROTOCOL_VERSION

    def __init__(self, observer):
        self.observer = observer
        self.started = False

    def start(self, uptime, version):
        """
        Called to start the handshaking negotiations.
        """
        if self.started:
            raise HandshakeError('Handshake negotiator cannot be restarted')

        self.started = True
        self.buffer = util.BufferedByteStream()

        self.peer_version = None

        self.my_syn = Packet(first=uptime, second=version)
        self.my_ack = None

        self.peer_syn = None
        self.peer_ack = None

    def getPeerPacket(self):
        """
        Attempts to decode a L{Packet} from the buffer. If there is not enough
        data in the buffer then C{None} is returned.
        """
        if self.buffer.remaining() < HANDSHAKE_LENGTH:
            # we're expecting more data
            return

        packet = Packet()

        packet.decode(self.buffer)

        return packet

    def writeVersionAndSyn(self):
        """
        Writes the handshake version and syn packet to the observer.
        """
        self.buffer.truncate()
        self.buffer.write_uchar(self.protocolVersion)

        self._writePacket(self.my_syn)

    def _writePacket(self, packet):
        packet.encode(self.buffer)

        data = self.buffer.getvalue()
        self.buffer.truncate()

        self.observer.write(data)

    def dataReceived(self, data):
        """
        Called when handshake data has been received. If an error occurs
        whilst negotiating the handshake then C{self.observer.handshakeFailure}
        will be called, citing the reason.

        3 stages of data are received. The handshake version, the syn packet and
        then the ack packet.
        """
        try:
            if not self.started:
                raise HandshakeError('Data was received, but negotiator was '
                    'not started')

            self.buffer.append(data)

            self._process()
        except:
            self.observer.handshakeFailure(*sys.exc_info())

    def _process(self):
        if not self.peer_version:
            if self.buffer.remaining() < 1:
                # we're expecting more data
                return

            self.peer_version = self.buffer.read_uchar()

            self.versionReceived()

        if not self.peer_syn:
            self.peer_syn = self.getPeerPacket()

            if not self.peer_syn:
                return

            self.synReceived()

        if not self.peer_ack:
            self.peer_ack = self.getPeerPacket()

            if not self.peer_ack:
                return

            self.ackReceived()

        # if we get here then a successful handshake has been negotiated.
        # inform the observer accordingly
        self.observer.handshakeSuccess()

    def writeAck(self):
        """
        Writes L{self.my_ack} to the observer.
        """
        self.buildAckPayload(self.my_ack)

        self.buffer.truncate()
        self._writePacket(self.my_ack)

    def buildSynPayload(self, packet):
        """
        Called to build the syn packet, based on the state of the negotiations.

        C{RTMP} payloads are just random.
        """
        generate_payload(packet)

    def buildAckPayload(self, packet):
        """
        Called to build the ack packet, based on the state of the negotiations.

        C{RTMP} payloads are just random.
        """
        generate_payload(packet)

    def versionReceived(self):
        """
        Called when the peers handshake version has been received.
        """
        if self.peer_version == self.protocolVersion:
            return

        if self.peer_version > MAX_PROTOCOL_VERSION:
            raise ProtocolVersionError('Invalid protocol version')

        if self.peer_version > self.protocolVersion:
            raise ProtocolTooHigh('Unexpected protocol version')

    def synReceived(self):
        """
        Called when the peers syn packet has been received. Use this function to
        do any validation/verification.
        """

    def ackReceived(self):
        """
        Called when the peers ack packet has been received. Use this function to
        do any validation/verification.
        """


class ClientNegotiator(BaseNegotiator):
    """
    Negotiator for client initiating handshakes.
    """

    def start(self, uptime, version):
        """
        Writes the handshake version and the syn packet.
        """
        BaseNegotiator.start(self, uptime, version)

        self.buildSynPayload(self.my_syn)

        self.writeVersionAndSyn()

    def versionReceived(self):
        """
        Called when the peers handshake version is received. If the peer offers
        a version lower than the version the client wants to speak, then the
        client will complain.
        """
        BaseNegotiator.versionReceived(self)

        if self.peer_version < self.protocolVersion:
            raise ProtocolDegraded('Protocol version did not match (got %d, '
                'expected %d)' % (self.peer_version, self.protocolVersion))

    def synReceived(self):
        """
        Called when the peers syn packet has been received. Use this function to
        do any validation/verification.

        We're waiting for the ack packet to be received before we do anything.
        """

    def ackReceived(self):
        """
        Called when the peers ack packet has been received. Use this function to
        do any validation/verification.

        If validation succeeds then the ack is sent.
        """
        if self.buffer.remaining() != 0:
            raise HandshakeError('Unexpected trailing data after peer ack')

        if self.peer_ack.first != self.my_syn.first:
            raise VerificationError('Received uptime is not the same')

        if self.peer_ack.payload != self.my_syn.payload:
            raise VerificationError('Received payload is not the same')

        self.my_ack = Packet(first=self.peer_syn.first,
            second=self.my_syn.timestamp)

        self.writeAck()


class ServerNegotiator(BaseNegotiator):
    """
    Negotiator for server handshakes.
    """

    def versionReceived(self):
        """
        Called when the peers version has been received.

        Builds and writes the syn packet.
        """
        BaseNegotiator.versionReceived(self)

        self.buildSynPayload(self.my_syn)

        self.writeVersionAndSyn()

    def synReceived(self):
        """
        Called when the client sends its syn packet.

        Builds and writes the ack packet.
        """
        self.my_ack = Packet(first=self.peer_syn.timestamp,
            second=self.my_syn.timestamp)

        self.writeAck()

    def ackReceived(self):
        """
        Called when the clients ack packet has been received.
        """
        if self.my_syn.first != self.peer_ack.first:
            raise VerificationError('Received uptime is not the same')

        if self.my_syn.payload != self.peer_ack.payload:
            raise VerificationError('Received payload does not match')


def generate_payload(packet):
    """
    Generates a random payload for RTMP handshakes.
    """
    packet.payload = util.generateBytes(HANDSHAKE_LENGTH - 8)
