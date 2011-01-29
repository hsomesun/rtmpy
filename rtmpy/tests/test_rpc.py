# Copyright the RTMPy Project
#
# RTMPy is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 2.1 of the License, or (at your option)
# any later version.
#
# RTMPy is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with RTMPy.  If not, see <http://www.gnu.org/licenses/>.

"""
Tests for L{rtmpy.rpc}.
"""


from zope.interface import implementedBy
from twisted.trial import unittest
from twisted.internet import defer

from rtmpy import rpc, message, exc



class ExposingTestCase(unittest.TestCase):
    """
    Tests for L{rpc.expose}.
    """


    def assertExposed(self, class_func, msg=None):
        cls = class_func.im_class
        name = class_func.__name__

        exposed_methods = rpc.getExposedMethods(cls)

        assert name in exposed_methods, \
            msg or '%r is not an exposed method on %r' % (name, cls)


    def assertExposedAs(self, class_func, as_, msg=None):
        cls = class_func.im_class
        name = class_func.__name__

        exposed_methods = rpc.getExposedMethods(cls)

        assert exposed_methods.get(as_, None) == name, \
            msg or '%r is not an exposed method on %r' % (name, cls)


    def assertNotExposed(self, class_func, msg=None):
        try:
            self.assertExposed(class_func)
        except AssertionError:
            pass
        else:
            cls = class_func.im_class
            name = class_func.__name__

            raise AssertionError(
                msg or '%r IS an exposed method on %r' % (name, cls))


    def test_simple(self):
        """
        Exposing methods on classes should return sane values for
        L{rpc.getExposedMethods}
        """
        class SomeClass(object):
            @rpc.expose
            def foo(self):
                pass


            @rpc.expose('me')
            def bar(self):
                pass


            def not_exposed(self):
                pass

        self.assertEqual(rpc.getExposedMethods(SomeClass),
            {'me': 'bar', 'foo': 'foo'})

        self.assertExposed(SomeClass.foo)
        self.assertNotExposed(SomeClass.not_exposed)
        self.assertExposedAs(SomeClass.bar, 'me')
        self.assertExposedAs(SomeClass.foo, 'foo')


    def test_deep(self):
        """
        As with L{test_simple} but a complex class hierarchy.
        """
        class A(object):
            @rpc.expose
            def anon(self):
                pass

            def nope(self):
                pass

        class B(A):
            @rpc.expose('bar')
            def named(self):
                pass


        self.assertEqual(rpc.getExposedMethods(A), {'anon': 'anon'})
        self.assertEqual(rpc.getExposedMethods(B),
            {'anon': 'anon', 'bar': 'named'})

        self.assertExposedAs(A.anon, 'anon')
        self.assertExposedAs(B.anon, 'anon')
        self.assertNotExposed(A.nope)
        self.assertNotExposed(B.nope)
        self.assertExposedAs(B.named, 'bar')


class CallHandlerTestCase(unittest.TestCase):
    """
    Tests for L{rpc.BaseCallHandler}.
    """

    def setUp(self):
        self.handler = rpc.BaseCallHandler()


    def test_initiate(self):
        """
        Initiating a call should store the context that was passed to the call
        and return a unique, incrementing id.
        """
        h = self.handler
        c = ('foo', ['bar', 'baz'], {})

        self.assertEqual(h.getNextCallId(), 1)
        self.assertEqual(h.getCallContext(1), None)

        self.assertEqual(h.initiateCall(*c), 1)
        self.assertEqual(h.getCallContext(1), c)

        self.assertEqual(h.getNextCallId(), 2)
        self.assertEqual(h.getCallContext(2), None)


    def test_active(self):
        """
        Ensure that L{rpc.BaseCallHandler.isCallActive} returns some sane
        results.
        """
        h = self.handler

        self.assertEqual(h.getNextCallId(), 1)

        self.assertFalse(h.isCallActive(1))

        callId = h.initiateCall()

        self.assertTrue(h.isCallActive(callId))


    def test_finish_non_active(self):
        """
        Finishing a call that is not active should result in no state change
        and C{None} should be returned.
        """
        h = self.handler
        hsh = hash(h)

        self.assertFalse(h.isCallActive(1))

        self.assertEqual(h.finishCall(1), None)
        self.assertEqual(hsh, hash(h))


    def test_finish_active_call(self):
        """
        Finishing an active call should return the original context supplied to
        C{initiateCall} and the call should no longer be active.
        """
        h = self.handler
        c = ('foo', ['bar', 'baz'], {})

        callId = h.initiateCall(*c)

        self.assertEqual(h.finishCall(callId), c)
        self.assertFalse(h.isCallActive(callId))


    def test_discard_non_active(self):
        """
        Discarding a call that is not active should result in no state change
        and C{None} should be returned.
        """
        h = self.handler
        hsh = hash(h)

        self.assertFalse(h.isCallActive(1))

        self.assertEqual(h.discardCall(1), None)
        self.assertEqual(hsh, hash(h))


    def test_discard_active_call(self):
        """
        Discarding an active call should return the original context supplied to
        C{initiateCall} and the call should no longer be active.
        """
        h = self.handler
        c = ('foo', ['bar', 'baz'], {})

        callId = h.initiateCall(*c)

        self.assertEqual(h.discardCall(callId), c)
        self.assertFalse(h.isCallActive(callId))



class AbstractCallInitiatorTestCase(unittest.TestCase):
    """
    Tests for L{rpc.AbstractCallInitiator}
    """


    def test_interface(self):
        """
        Check defined interfaces.
        """
        self.assertTrue(
            message.IMessageSender.implementedBy(rpc.AbstractCallInitiator))


    def test_send_message(self):
        """
        Abstract methods should raise C{NotImplementedError}.
        """
        a = rpc.AbstractCallInitiator()

        self.assertRaises(NotImplementedError, a.sendMessage, None)



class SimpleInvoker(rpc.AbstractCallInitiator):
    """
    An implementation of L{rpc.AbstractCallInitiator} that stores any messages
    were sent for later inspection.

    @messages
    """

    def __init__(self):
        super(rpc.AbstractCallInitiator, self).__init__()

        self.messages = []


    def sendMessage(self, msg):
        """
        Keeps track of any messages that were 'sent'.
        """
        self.messages.append(msg)



class CallTestCase(unittest.TestCase):
    """
    Tests for L{rpc.AbstractCallInitiator.call}
    """


    def setUp(self):
        self.invoker = SimpleInvoker()
        self.messages = self.invoker.messages


    def test_call_message(self):
        """
        Check the context of the message sent when L{call} is executed.
        """
        i = self.invoker
        m = self.messages

        i.call('remote_method', 1, 2, 3, 'foo')

        self.assertEqual(len(m), 1)
        msg = m.pop()

        self.assertEqual(message.typeByClass(msg), message.INVOKE)
        self.assertEqual(msg.id, 0)
        self.assertEqual(msg.name, 'remote_method')
        self.assertEqual(msg.argv, [None, 1, 2, 3, 'foo'])


    def test_call_command(self):
        """
        Ensure L{call} accepts a C{command} kwarg and that it is set on
        the message appropriately.
        """
        cmd = {'foo': 'bar'}
        i, m = self.invoker, self.messages

        i.call('remote_method', command=cmd)

        self.assertEqual(len(m), 1)
        msg = m.pop()

        self.assertEqual(message.typeByClass(msg), message.INVOKE)
        self.assertEqual(msg.id, 0)
        self.assertEqual(msg.name, 'remote_method')
        self.assertEqual(msg.argv, [cmd])


    def test_call_tracking(self):
        """
        Any call to L{call} should not be considered 'active'.
        """
        i = self.invoker

        i.call('foo')

        self.assertFalse(i.isCallActive(0))



class CallWithResultTestCase(unittest.TestCase):
    """
    Tests for L{rpc.AbstractCallInitiator.callWithResult}
    """


    def setUp(self):
        self.invoker = SimpleInvoker()
        self.messages = self.invoker.messages


    def test_call(self):
        """
        Check the context of the message sent when L{callWithResult} is
        executed.
        """
        i = self.invoker
        m = self.messages

        d = i.callWithResult('remote_method', 1, 2, 3, 'foo')

        self.assertTrue(isinstance(d, defer.Deferred))
        self.assertEqual(len(m), 1)
        msg = m.pop()

        self.assertEqual(message.typeByClass(msg), message.INVOKE)
        self.assertEqual(msg.id, 1)
        self.assertEqual(msg.name, 'remote_method')
        self.assertEqual(msg.argv, [None, 1, 2, 3, 'foo'])

        callContext = i.getCallContext(msg.id)

        self.assertEqual(callContext,
            (d, 'remote_method', (1, 2, 3, 'foo'), None))


    def test_command(self):
        """
        Ensure L{callWithResult} accepts a C{command} kwarg and that it
        is set on the sent message appropriately.
        """
        cmd = {'foo': 'bar'}
        i, m = self.invoker, self.messages

        d = i.callWithResult('remote_method', command=cmd)

        self.assertTrue(isinstance(d, defer.Deferred))
        self.assertEqual(len(m), 1)
        msg = m.pop()

        self.assertEqual(message.typeByClass(msg), message.INVOKE)
        self.assertEqual(msg.id, 1)
        self.assertEqual(msg.name, 'remote_method')
        self.assertEqual(msg.argv, [cmd])

        callContext = i.getCallContext(msg.id)

        self.assertEqual(callContext,
            (d, 'remote_method', (), cmd))


    def test_send_failure(self):
        """
        Ensure correct state when sending a message blows up.
        """
        class TestRuntimeError(RuntimeError):
            """
            """

        def sendBadMessage(msg):
            self.msg = msg

            raise TestRuntimeError(msg)

        i = self.invoker

        self.patch(i, 'sendMessage', sendBadMessage)

        self.assertRaises(TestRuntimeError, i.callWithResult,
            'remote_method')

        self.assertFalse(i.isCallActive(self.msg.id))



class CallResponseTestCase(unittest.TestCase):
    """
    Tests the response to an RPC call.
    """


    def setUp(self):
        self.invoker = SimpleInvoker()
        self.messages = self.invoker.messages


    def sendResponse(self, responseType, callId, *args, **kwargs):
        """
        Build an RPC response.

        @param responseType: Either C{_result} or C{_error}.
        @param callId: The id of the response.
        @param args: The args to supply as part of the response.
        """
        self.invoker.handleResponse(responseType, callId, args, **kwargs)


    def makeCall(self, name, *args, **kwargs):
        """
        """
        return self.invoker.callWithResult(name, *args, **kwargs)


    def test_unknown_call_id(self):
        """
        Send a response to a non existant RPC call.
        """
        i = self.invoker

        self.assertFalse(i.isCallActive(0))
        self.sendResponse(None, 0)

        self.assertFalse(i.isCallActive(1))
        self.sendResponse(None, 1)


    def test_success_result(self):
        """
        Ensure that the deferred handed back in L{callWithResult} has its
        callback called if a success response is received for the corresponding
        call id.

        The callback should contain the args of the response
        """
        d = self.makeCall('some_remote_method')
        self.executed = False

        def cb(args):
            self.executed = True

            self.assertEqual(args, ('foo', 'bar'))

        d.addCallback(cb)

        self.sendResponse('_result', 1, 'foo', 'bar')

        self.assertTrue(self.executed)
        self.assertFalse(self.invoker.isCallActive(1))


    def test_error_result(self):
        """
        Ensure that the deferred handed back in L{callWithResult} has its
        errback called if an error response is received for the corresponding
        call id.

        """
        d = self.makeCall('some_remote_method')
        self.executed = False

        def eb(fail):
            self.executed = True

            self.assertIsInstance(fail, rpc.RemoteCallFailed)
            self.assertEqual(fail.value, ('foo', 'bar'))


        d.addCallback(lambda _: self.fail('Callback called'))
        d.addErrback(eb)

        self.sendResponse('_error', 1, 'foo', 'bar')

        self.assertTrue(self.executed)
        self.assertFalse(self.invoker.isCallActive(1))


    def test_command(self):
        """
        Ensure that a command kwarg is acceptable by L{handleResponse}.
        """
        d = self.makeCall('some_remote_method')
        self.executed = False

        def cb(res):
            self.executed = True


        d.addCallback(cb)

        self.sendResponse('_result', 1, 'foo', 'bar', command={'foo': 'bar'})

        self.assertTrue(self.executed)
        self.assertFalse(self.invoker.isCallActive(1))


    def test_unknown_response(self):
        """
        Ensure that the deferred is not called if the response name is not
        recognised.
        """
        d = self.makeCall('some_remote_method')

        d.addBoth(lambda: self.fail('deferred executed!'))

        self.sendResponse('foo', 1, 'some result')

        self.assertFalse(self.invoker.isCallActive(1))



class AbstractRemoteHandlerTestCase(unittest.TestCase):
    """
    Tests for L{rpc.AbstractRemoteHandler}
    """


    def test_interface(self):
        """
        Check defined interfaces.
        """
        self.assertTrue(
            message.IMessageSender.implementedBy(rpc.AbstractCallFacilitator))


    def test_send_message(self):
        """
        Abstract methods should raise C{NotImplementedError}.
        """
        a = rpc.AbstractCallFacilitator()

        self.assertRaises(NotImplementedError, a.sendMessage, None)



class CallingExposedMethodTestCase(unittest.TestCase):
    """
    Tests for L{rpc.callExposedMethod}
    """

    class Foo(object):

        def __init__(self, test):
            self.test = test


        @rpc.expose
        def exposed(self, *args):
            self.test.assertEqual(args, self.expectedArgs)

            return self.expectedReturn


        @rpc.expose('named')
        def exposed_named(self, *args):
            self.test.assertEqual(args, self.expectedArgs)

            return self.expectedReturn


        def not_exposed(self, *args):
            self.test.assertEqual(args, self.expectedArgs)

            return self.expectedReturn



    def setUp(self):
        self.instance = self.Foo(self)


    def call(self, name, expectedArgs, expectedReturn):
        self.instance.expectedArgs = expectedArgs
        self.instance.expectedReturn = expectedReturn

        self.assertEqual(rpc.callExposedMethod(
            self.instance, name, *expectedArgs), expectedReturn)


    def test_exposed_unnamed(self):
        """
        Test unnamed.
        """
        self.call('exposed', (1, 2, 3), 'foo')


    def test_exposed_named(self):
        """
        Test named exposed function for args and return.
        """
        self.call('named', (1, 2, 3), 'foo')
        e = self.assertRaises(exc.CallFailed,
            self.call, 'exposed_named', (1, 2, 3), 'foo')

        self.assertEqual(str(e), "Unknown method 'exposed_named'")


    def test_not_exposed(self):
        """
        Ensure that calling an unexposed method results in a L{exc.CallFailed}
        exception.
        """
        e = self.assertRaises(exc.CallFailed,
            self.call, 'not_exposed', (), None)

        self.assertEqual(str(e), "Unknown method 'not_exposed'")