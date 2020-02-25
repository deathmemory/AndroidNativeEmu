import logging
import os

from androidemu.hooker import Hooker
from androidemu.internal.modules import Modules
from androidemu.native.memory import NativeMemory

from androidemu.java.helpers.native_method import native_method
from androidemu.utils import memory_helpers

logger = logging.getLogger(__name__)


class NativeHooks:
    """
    :type memory NativeMemory
    :type modules Modules
    :type hooker Hooker
    """

    def __init__(self, emu, memory, modules, hooker):
        self._emu = emu
        self._memory = memory
        self._modules = modules
        self.atexit = []

        modules.add_symbol_hook('__system_property_get', hooker.write_function(self.system_property_get) + 1)
        modules.add_symbol_hook('dlopen', hooker.write_function(self.dlopen) + 1)
        modules.add_symbol_hook('dlclose', hooker.write_function(self.dlclose) + 1)
        modules.add_symbol_hook('dladdr', hooker.write_function(self.dladdr) + 1)
        modules.add_symbol_hook('dlsym', hooker.write_function(self.dlsym) + 1)
        modules.add_symbol_hook('pthread_create', hooker.write_function(self.nop('pthread_create')) + 1)
        modules.add_symbol_hook('pthread_join', hooker.write_function(self.nop('pthread_join')) + 1)
        modules.add_symbol_hook('vfprintf', hooker.write_function(self.nop('vfprintf')) + 1)
        modules.add_symbol_hook('fprintf', hooker.write_function(self.nop('fprintf')) + 1)
        modules.add_symbol_hook('dlerror', hooker.write_function(self.nop('dlerror')) + 1)

    @native_method
    def system_property_get(self, uc, name_ptr, buf_ptr):
        name = memory_helpers.read_utf8(uc, name_ptr)
        logger.debug("Called __system_property_get(%s, 0x%x)" % (name, buf_ptr))

        if name in self._emu.system_properties:
            memory_helpers.write_utf8(uc, buf_ptr, self._emu.system_properties[name])
        else:
            raise ValueError('%s was not found in system_properties dictionary.' % name)

        return None

    @native_method
    def dlopen(self, uc, path):
        path = memory_helpers.read_utf8(uc, path)
        logger.debug("Called dlopen(%s)" % path)

        if path == 'libvendorconn.so':
            lib = os.path.realpath(os.path.join(__file__, '..', '..', '..', 'samples', 'example_binaries', 'libvendorconn.so'))
            mod = self._emu.load_library(lib)

            return mod.base

        return None

    @native_method
    def dlclose(self, uc, handle):
        """
        The function dlclose() decrements the reference count on the dynamic library handle handle.
        If the reference count drops to zero and no other loaded libraries use symbols in it, then the dynamic library is unloaded.
        """
        logger.debug("Called dlclose(0x%x)" % handle)
        return 0

    @native_method
    def dladdr(self, uc, addr, info):
        logger.debug("Called dladdr(0x%x, 0x%x)" % (addr, info))

        infos = memory_helpers.read_uints(uc, info, 4)
        Dl_info = {}

        nm = self._emu.native_memory
        isfind = False
        for mod in self._modules.modules:
            if mod.base <= addr < mod.base + mod.size:
                dli_fname = nm.allocate(len(mod.filename) + 1)
                memory_helpers.write_utf8(uc, dli_fname, mod.filename + '\x00')
                memory_helpers.write_uints(uc, addr, [dli_fname, mod.base, 0, 0])
                return 1

    @native_method
    def dlsym(self, uc, handle, symbol):
        symbol_str = memory_helpers.read_utf8(uc, symbol)
        logger.debug("Called dlsym(0x%x, %s)" % (handle, symbol_str))

        if handle == 0xffffffff:
            sym = self._modules.find_symbol_str(symbol_str)
        else:
            module = self._modules.find_module(handle)

            if module is None:
                raise Exception('Module not found for address 0x%x' % symbol)

            sym = module.find_symbol(symbol)

        if sym is None:
            return 0

        raise NotImplementedError

    def nop(self, name):
        @native_method
        def nop_inside(emu):
            raise NotImplementedError('Symbol hook not implemented %s' % name)
        return nop_inside
