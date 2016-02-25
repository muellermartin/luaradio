#!/usr/bin/env python3

import scipy.signal
import random
import numpy

# Floating point precision to round and serialize to
PRECISION = 8

# Default comparison epsilon
EPSILON = 1e-6

# Fixed random seed for deterministic generation
random.seed(1)

################################################################################
# Helper functions for generating random types
################################################################################

def random_complex64(n):
    return numpy.around(numpy.array([complex(2*random.random()-1.0, 2*random.random()-1.0) for _ in range(n)]).astype(numpy.complex64), PRECISION)

def random_float32(n):
    return numpy.around(numpy.array([2*random.random()-1.0 for _ in range(n)]).astype(numpy.float32), PRECISION)

def random_integer32(n):
    return numpy.array([random.randint(-2147483648, 2147483647) for _ in range(n)]).astype(numpy.int32)

def random_bit(n):
    return numpy.array([random.randint(0, 1) for _ in range(n)]).astype(numpy.bool_)

################################################################################
# Serialization Python to Lua functions
################################################################################

NUMPY_SERIALIZE_TYPE = {
    numpy.complex64: lambda x: "{%.*f, %.*f}" % (PRECISION, x.real, PRECISION, x.imag),
    numpy.float32: lambda x: "%.*f" % (PRECISION, x),
    numpy.int32: lambda x: "%d" % x,
    numpy.bool_: lambda x: "%d" % x,
}

NUMPY_VECTOR_TYPE = {
    numpy.complex64: "radio.ComplexFloat32Type.vector_from_array({%s})",
    numpy.float32: "radio.Float32Type.vector_from_array({%s})",
    numpy.int32: "radio.Integer32Type.vector_from_array({%s})",
    numpy.bool_: "radio.BitType.vector_from_array({%s})",
}

class CustomVector(object):
    pass

def serialize(x):
    if isinstance(x, list):
        t = [serialize(e) for e in x]
        return "{" + ", ".join(t) + "}"
    elif isinstance(x, numpy.ndarray):
        t = [NUMPY_SERIALIZE_TYPE[type(x[0])](e) for e in x]
        return NUMPY_VECTOR_TYPE[type(x[0])] % ", ".join(t)
    elif isinstance(x, CustomVector):
        return x.serialize()
    else:
        return str(x)

################################################################################

def generate_test_vector(func, args, inputs, note=None):
    outputs = func(*(args + inputs))

    tab = " "*4

    s = tab + "{" + ((" -- " + note + "\n") if note else "\n")
    s += tab + tab + "args = {" + ", ".join([serialize(e) for e in args]) + "},\n"
    s += tab + tab + "inputs = {" + ", ".join([serialize(e) for e in inputs]) + "},\n"
    s += tab + tab + "outputs = {" + ", ".join([serialize(e) for e in outputs]) + "}\n"
    s += tab + "},\n"
    return s

def generate_spec(block_name, test_vectors, epsilon):
    s = "local radio = require('radio')\n"
    s += "local jigs = require('tests.jigs')\n"
    s += "\n"
    s += "jigs.TestBlock(radio.%s, {\n" % block_name
    s += "".join(test_vectors)
    s += "}, {epsilon = %.1e})\n" % epsilon
    return s

def write_to(filename, text):
    with open(filename, "w") as f:
        f.write(text)

################################################################################
# Decorators for spec generator functions
################################################################################

AllSpecs = []

def block_spec(block_name, filename, epsilon=EPSILON):
    def wrap(f):
        def wrapped():
            test_vectors = f()
            spec = generate_spec(block_name, test_vectors, epsilon)
            write_to(filename, spec)
        AllSpecs.append(wrapped)
        return wrapped

    return wrap

def raw_spec(filename):
    def wrap(f):
        def wrapped():
            spec = f()
            write_to(filename, "\n".join(spec))
        AllSpecs.append(wrapped)
        return wrapped

    return wrap

################################################################################
# Filter generation helper functions not available in numpy/scipy
################################################################################

def fir_root_raised_cosine(num_taps, sample_rate, beta, symbol_period):
    h = []

    assert (num_taps % 2) == 1, "Number of taps must be odd."

    for i in range(num_taps):
        t = (i - (num_taps-1)/2)/sample_rate

        if t == 0:
            h.append((1/(numpy.sqrt(symbol_period))) * (1-beta+4*beta/numpy.pi))
        elif numpy.isclose(t, -symbol_period/(4*beta)) or numpy.isclose(t, symbol_period/(4*beta)):
            h.append((beta/numpy.sqrt(2*symbol_period))*((1+2/numpy.pi)*numpy.sin(numpy.pi/(4*beta))+(1-2/numpy.pi)*numpy.cos(numpy.pi/(4*beta))))
        else:
            num = numpy.cos((1 + beta)*numpy.pi*t/symbol_period) + numpy.sin((1 - beta)*numpy.pi*t/symbol_period)/(4*beta*t/symbol_period)
            denom = (1 - (4*beta*t/symbol_period)*(4*beta*t/symbol_period))
            h.append(((4*beta)/(numpy.pi*numpy.sqrt(symbol_period)))*num/denom)

    h = numpy.array(h)/numpy.sum(h)

    return h.astype(numpy.float32)

def fir_hilbert_transform(num_taps, window_func):
    h = []

    assert (num_taps % 2) == 1, "Number of taps must be odd."

    for i in range(num_taps):
        i_shifted = (i - (num_taps-1)/2)
        h.append(0 if (i_shifted % 2) == 0 else 2/(i_shifted*numpy.pi))

    h = h * window_func(num_taps)

    return h.astype(numpy.float32)

################################################################################

@block_spec("FIRFilterBlock", "tests/blocks/signal/firfilter_spec.lua")
def generate_firfilter_spec():
    def process(taps, x):
        return [scipy.signal.lfilter(taps, 1, x).astype(type(x[0]))]

    normalize = lambda v: v / numpy.sum(numpy.abs(v))

    vectors = []
    x = random_complex64(256)
    vectors.append(generate_test_vector(process, [normalize(random_float32(1))], [x], "1 Float32 tap, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [normalize(random_float32(8))], [x], "8 Float32 tap, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [normalize(random_float32(15))], [x], "15 Float32 tap, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [normalize(random_float32(128))], [x], "128 Float32 tap, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    x = random_float32(256)
    vectors.append(generate_test_vector(process, [normalize(random_float32(1))], [x], "1 Float32 tap, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [normalize(random_float32(8))], [x], "8 Float32 tap, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [normalize(random_float32(15))], [x], "15 Float32 tap, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [normalize(random_float32(128))], [x], "128 Float32 tap, 256 Float32 input, 256 Float32 output"))

    return vectors

@block_spec("IIRFilterBlock", "tests/blocks/signal/iirfilter_spec.lua")
def generate_iirfilter_spec():
    def gentaps(n):
        b, a = scipy.signal.butter(n-1, 0.5)
        b = numpy.around(b, PRECISION)
        a = numpy.around(a, PRECISION)
        return [b.astype(numpy.float32), a.astype(numpy.float32)]

    def process(b_taps, a_taps, x):
        return [scipy.signal.lfilter(b_taps, a_taps, x).astype(type(x[0]))]

    vectors = []
    x = random_complex64(256)
    vectors.append(generate_test_vector(process, gentaps(3), [x], "3 Float32 b taps, 3 Float32 a taps, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, gentaps(5), [x], "5 Float32 b taps, 5 Float32 a taps, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, gentaps(10), [x], "10 Float32 b taps, 10 Float32 a taps, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    x = random_float32(256)
    vectors.append(generate_test_vector(process, gentaps(3), [x], "3 Float32 b taps, 3 Float32 a taps, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, gentaps(5), [x], "5 Float32 b taps, 5 Float32 a taps, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, gentaps(10), [x], "10 Float32 b taps, 10 Float32 a taps, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))

    return vectors

@block_spec("MultiplyBlock", "tests/blocks/signal/multiply_spec.lua")
def generate_multiply_spec():
    def process(x, y):
        return [x * y]

    vectors = []
    x = random_complex64(256)
    y = random_complex64(256)
    vectors.append(generate_test_vector(process, [], [x, y], "2 256 ComplexFloat32 inputs, 256 ComplexFloat32 output"))
    x = random_float32(256)
    y = random_float32(256)
    vectors.append(generate_test_vector(process, [], [x, y], "2 256 Float32 inputs, 256 Float32 output"))

    return vectors

@block_spec("MultiplyConjugateBlock", "tests/blocks/signal/multiplyconjugate_spec.lua")
def generate_multiplyconjugate_spec():
    def process(x, y):
        return [x * numpy.conj(y)]

    vectors = []
    x = random_complex64(256)
    y = random_complex64(256)
    vectors.append(generate_test_vector(process, [], [x, y], "2 256 ComplexFloat32 inputs, 256 ComplexFloat32 output"))

    return vectors

@block_spec("SumBlock", "tests/blocks/signal/sum_spec.lua")
def generate_sum_spec():
    def process(x, y):
        return [x + y]

    vectors = []
    x, y = random_complex64(256), random_complex64(256)
    vectors.append(generate_test_vector(process, [], [x, y], "2 256 ComplexFloat32 inputs, 256 ComplexFloat32 output"))
    x, y = random_float32(256), random_float32(256)
    vectors.append(generate_test_vector(process, [], [x, y], "2 256 Float32 inputs, 256 Float32 output"))
    x, y = random_integer32(256), random_integer32(256)
    vectors.append(generate_test_vector(process, [], [x, y], "2 256 Integer32 inputs, 256 Integer32 output"))

    return vectors

@block_spec("ComplexToRealBlock", "tests/blocks/signal/complextoreal_spec.lua")
def generate_complextoreal_spec():
    def process(x):
        return [numpy.real(x)]

    vectors = []
    x = random_complex64(256)
    vectors.append(generate_test_vector(process, [], [x], "256 ComplexFloat32 input, 256 Float32 output"))

    return vectors

@block_spec("SlicerBlock", "tests/blocks/signal/slicer_spec.lua")
def generate_slicer_spec():
    def process(threshold, x):
        return [x > threshold]

    vectors = []
    x = random_float32(256)
    vectors.append(generate_test_vector(process, [0.00], [x], "Default threshold, 256 Float32 input, 256 Bit output"))
    vectors.append(generate_test_vector(process, [0.25], [x], "0.25 threshold, 256 Float32 input, 256 Bit output"))
    vectors.append(generate_test_vector(process, [-0.25], [x], "-0.25 threshold, 256 Float32 input, 256 Bit output"))

    return vectors

@block_spec("DifferentialDecoderBlock", "tests/blocks/signal/differentialdecoder_spec.lua")
def generate_differentialdecoder_spec():
    def process(x):
        prev_bit = numpy.bool_(False)
        return [numpy.logical_xor(numpy.insert(x, 0, False)[:-1], x)]

    vectors = []
    x = random_bit(256)
    vectors.append(generate_test_vector(process, [], [x], "256 Bit input, 256 Bit output"))

    return vectors

@block_spec("DelayBlock", "tests/blocks/signal/delay_spec.lua")
def generate_delay_spec():
    def process(n, x):
        elem_type = type(x[0])
        return [numpy.insert(x, 0, [elem_type()]*n)[:len(x)]]

    vectors = []
    x = random_complex64(256)
    vectors.append(generate_test_vector(process, [1], [x], "1 Sample Delay, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [15], [x], "1 Sample Delay, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [100], [x], "1 Sample Delay, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    x = random_float32(256)
    vectors.append(generate_test_vector(process, [1], [x], "1 Sample Delay, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [15], [x], "1 Sample Delay, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [100], [x], "1 Sample Delay, 256 Float32 input, 256 Float32 output"))
    x = random_integer32(256)
    vectors.append(generate_test_vector(process, [1], [x], "1 Sample Delay, 256 Integer32 input, 256 Integer32 output"))
    vectors.append(generate_test_vector(process, [15], [x], "1 Sample Delay, 256 Integer32 input, 256 Integer32 output"))
    vectors.append(generate_test_vector(process, [100], [x], "1 Sample Delay, 256 Integer32 input, 256 Integer32 output"))

    return vectors

@block_spec("FrequencyDiscriminatorBlock", "tests/blocks/signal/frequencydiscriminator_spec.lua")
def generate_frequencydiscriminator_spec():
    def process(gain, x):
        x_shifted = numpy.insert(x, 0, numpy.complex64())[:len(x)]
        tmp = x*numpy.conj(x_shifted)
        return [(numpy.arctan2(numpy.imag(tmp), numpy.real(tmp))/gain).astype(numpy.float32)]

    vectors = []
    x = random_complex64(256)
    vectors.append(generate_test_vector(process, [1.0], [x], "1.0 Gain, 256 ComplexFloat32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [5.0], [x], "5.0 Gain, 256 ComplexFloat32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [10.0], [x], "10.0 Gain, 256 ComplexFloat32 input, 256 Float32 output"))

    return vectors

@block_spec("SamplerBlock", "tests/blocks/signal/sampler_spec.lua")
def generate_sampler_spec():
    def process(data, clock):
        sampled_data = []
        hysteresis = False

        for i in range(len(clock)):
            if hysteresis == False and clock[i] > 0:
                sampled_data.append(data[i])
                hysteresis = True
            elif hysteresis == True and clock[i] < 0:
                hysteresis = False

        return [numpy.array(sampled_data)]

    vectors = []
    data, clk = random_complex64(256), random_float32(256)
    vectors.append(generate_test_vector(process, [], [data, clk], "256 ComplexFloat32 data, 256 Float32 clock, 256 Float32 output"))
    data, clk = random_float32(256), random_float32(256)
    vectors.append(generate_test_vector(process, [], [data, clk], "256 Float32 data, 256 Float32 clock, 256 Float32 output"))

    return vectors

@block_spec("DownsamplerBlock", "tests/blocks/signal/downsampler_spec.lua")
def generate_downsampler_spec():
    def process(factor, x):
        out = []

        for i in range(0, len(x), factor):
            out.append(x[i])

        return [numpy.array(out)]

    vectors = []
    x = random_complex64(256)
    vectors.append(generate_test_vector(process, [1], [x], "1 Factor, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [2], [x], "2 Factor, 256 ComplexFloat32 input, 128 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [3], [x], "3 Factor, 256 ComplexFloat32 input, 85 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [4], [x], "4 Factor, 256 ComplexFloat32 input, 64 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [7], [x], "7 Factor, 256 ComplexFloat32 input, 36 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [16], [x], "16 Factor, 256 ComplexFloat32 input, 16 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [128], [x], "128 Factor, 256 ComplexFloat32 input, 2 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [200], [x], "200 Factor, 256 ComplexFloat32 input, 1 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [256], [x], "256 Factor, 256 ComplexFloat32 input, 1 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [257], [x], "256 Factor, 256 ComplexFloat32 input, 0 ComplexFloat32 output"))
    x = random_float32(256)
    vectors.append(generate_test_vector(process, [1], [x], "1 Factor, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [2], [x], "2 Factor, 256 Float32 input, 128 Float32 output"))
    vectors.append(generate_test_vector(process, [3], [x], "3 Factor, 256 Float32 input, 85 Float32 output"))
    vectors.append(generate_test_vector(process, [4], [x], "4 Factor, 256 Float32 input, 64 Float32 output"))
    vectors.append(generate_test_vector(process, [7], [x], "7 Factor, 256 Float32 input, 36 Float32 output"))
    vectors.append(generate_test_vector(process, [16], [x], "16 Factor, 256 Float32 input, 16 Float32 output"))
    vectors.append(generate_test_vector(process, [128], [x], "128 Factor, 256 Float32 input, 2 Float32 output"))
    vectors.append(generate_test_vector(process, [200], [x], "200 Factor, 256 Float32 input, 1 Float32 output"))
    vectors.append(generate_test_vector(process, [256], [x], "256 Factor, 256 Float32 input, 1 Float32 output"))
    vectors.append(generate_test_vector(process, [257], [x], "256 Factor, 256 Float32 input, 0 Float32 output"))
    x = random_integer32(256)
    vectors.append(generate_test_vector(process, [1], [x], "1 Factor, 256 Integer32 input, 256 Integer32 output"))
    vectors.append(generate_test_vector(process, [2], [x], "2 Factor, 256 Integer32 input, 128 Integer32 output"))
    vectors.append(generate_test_vector(process, [3], [x], "3 Factor, 256 Integer32 input, 85 Integer32 output"))
    vectors.append(generate_test_vector(process, [4], [x], "4 Factor, 256 Integer32 input, 64 Integer32 output"))
    vectors.append(generate_test_vector(process, [7], [x], "7 Factor, 256 Integer32 input, 36 Integer32 output"))
    vectors.append(generate_test_vector(process, [16], [x], "16 Factor, 256 Integer32 input, 16 Integer32 output"))
    vectors.append(generate_test_vector(process, [128], [x], "128 Factor, 256 Integer32 input, 2 Integer32 output"))
    vectors.append(generate_test_vector(process, [200], [x], "200 Factor, 256 Integer32 input, 1 Integer32 output"))
    vectors.append(generate_test_vector(process, [256], [x], "256 Factor, 256 Integer32 input, 1 Integer32 output"))
    vectors.append(generate_test_vector(process, [257], [x], "256 Factor, 256 Integer32 input, 0 Integer32 output"))

    return vectors

@block_spec("HilbertTransformBlock", "tests/blocks/signal/hilberttransform_spec.lua")
def generate_hilberttransform_spec():
    def process(num_taps, x):
        delay = int((num_taps-1)/2)
        h = fir_hilbert_transform(num_taps, scipy.signal.hamming)

        imag = scipy.signal.lfilter(h, 1, x).astype(numpy.float32)
        real = numpy.insert(x, 0, [numpy.float32()]*delay)[:len(x)]
        return [numpy.array([complex(*e) for e in zip(real, imag)]).astype(numpy.complex64)]

    vectors = []
    x = random_float32(256)
    vectors.append(generate_test_vector(process, [9], [x], "9 taps, 256 Float32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [65], [x], "65 taps, 256 Float32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [129], [x], "129 taps, 256 Float32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [257], [x], "257 taps, 256 Float32 input, 256 ComplexFloat32 output"))

    return vectors

@block_spec("BinaryPhaseCorrectorBlock", "tests/blocks/signal/binaryphasecorrector_spec.lua")
def generate_binaryphasecorrector_spec():
    def process(num_samples, x):
        phi_state = [0.0]*num_samples
        out = []

        for e in x:
            phi = numpy.arctan2(e.imag, e.real)
            phi = (phi + numpy.pi) if phi < -numpy.pi/2 else phi
            phi = (phi - numpy.pi) if phi > numpy.pi/2 else phi
            phi_state = phi_state[1:] + [phi]
            phi_avg = numpy.mean(phi_state)

            out.append(e * numpy.complex64(complex(numpy.cos(-phi_avg), numpy.sin(-phi_avg))))

        return [numpy.array(out)]

    vectors = []
    x = random_complex64(256)
    vectors.append(generate_test_vector(process, [4], [x], "4 sample average, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [17], [x], "17 sample average, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [64], [x], "64 sample average, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [100], [x], "100 sample average, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))

    return vectors

@raw_spec("tests/blocks/signal/filter_utils_vectors.lua")
def generate_filter_utils_spec():
    vectors = []

    # Header
    vectors.append("local radio = require('radio')")
    vectors.append("")
    vectors.append("local M = {}")

    # Window functions
    vectors.append("M.window_rectangular = " + serialize(scipy.signal.boxcar(128).astype(numpy.float32)))
    vectors.append("M.window_hamming = " + serialize(scipy.signal.hamming(128).astype(numpy.float32)))
    vectors.append("M.window_hanning = " + serialize(scipy.signal.hanning(128).astype(numpy.float32)))
    vectors.append("M.window_bartlett = " + serialize(scipy.signal.bartlett(128).astype(numpy.float32)))
    vectors.append("M.window_blackman = " + serialize(scipy.signal.blackman(128).astype(numpy.float32)))
    vectors.append("")

    # Firwin functions
    vectors.append("M.firwin_lowpass = " + serialize(scipy.signal.firwin(128, 0.5, scale=False).astype(numpy.float32)))
    vectors.append("M.firwin_highpass = " + serialize(scipy.signal.firwin(129, 0.5, pass_zero=False, scale=False).astype(numpy.float32)))
    vectors.append("M.firwin_bandpass = " + serialize(scipy.signal.firwin(129, [0.4, 0.6], pass_zero=False, scale=False).astype(numpy.float32)))
    vectors.append("M.firwin_bandstop = " + serialize(scipy.signal.firwin(129, [0.4, 0.6], scale=False).astype(numpy.float32)))
    vectors.append("")

    # FIR Root Raised Cosine function
    vectors.append("M.fir_root_raised_cosine = " + serialize(fir_root_raised_cosine(101, 1e6, 0.5, 1e3)))
    vectors.append("")

    # FIR Root Raised Cosine function
    vectors.append("M.fir_hilbert_transform = " + serialize(fir_hilbert_transform(129, scipy.signal.hamming)))
    vectors.append("")

    vectors.append("return M")

    return vectors

@block_spec("FrequencyTranslatorBlock", "tests/blocks/signal/frequencytranslator_spec.lua", epsilon=1e-5)
def generate_frequencytranslator_spec():
    # FIXME why does this need 1e-5 epsilon?
    def process(offset, x):
        rotator = numpy.exp(1j*2*numpy.pi*(offset/2.0)*numpy.arange(len(x))).astype(numpy.complex64)
        return [x * rotator]

    vectors = []
    x = random_complex64(256)
    vectors.append(generate_test_vector(process, [0.2], [x], "0.2 offset, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [0.5], [x], "0.5 offset, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [0.7], [x], "0.7 offset, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))

    return vectors

@block_spec("LowpassFilterBlock", "tests/blocks/signal/lowpassfilter_spec.lua")
def generate_lowpassfilter_spec():
    def process(num_taps, cutoff, x):
        b = scipy.signal.firwin(num_taps, cutoff, scale=False)
        return [scipy.signal.lfilter(b, 1, x).astype(type(x[0]))]

    vectors = []
    x = random_complex64(256)
    vectors.append(generate_test_vector(process, [128, 0.2], [x], "128 taps, 0.2 cutoff, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [128, 0.5], [x], "128 taps, 0.5 cutoff, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [128, 0.7], [x], "128 taps, 0.7 cutoff, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    x = random_float32(256)
    vectors.append(generate_test_vector(process, [128, 0.2], [x], "128 taps, 0.2 cutoff, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [128, 0.5], [x], "128 taps, 0.5 cutoff, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [128, 0.7], [x], "128 taps, 0.7 cutoff, 256 Float32 input, 256 Float32 output"))

    return vectors

@block_spec("HighpassFilterBlock", "tests/blocks/signal/highpassfilter_spec.lua")
def generate_highpassfilter_spec():
    def process(num_taps, cutoff, x):
        b = scipy.signal.firwin(num_taps, cutoff, pass_zero=False, scale=False)
        return [scipy.signal.lfilter(b, 1, x).astype(type(x[0]))]

    vectors = []
    x = random_complex64(256)
    vectors.append(generate_test_vector(process, [129, 0.2], [x], "129 taps, 0.2 cutoff, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [129, 0.5], [x], "129 taps, 0.5 cutoff, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [129, 0.7], [x], "129 taps, 0.7 cutoff, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    x = random_float32(256)
    vectors.append(generate_test_vector(process, [129, 0.2], [x], "129 taps, 0.2 cutoff, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [129, 0.5], [x], "129 taps, 0.5 cutoff, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [129, 0.7], [x], "129 taps, 0.7 cutoff, 256 Float32 input, 256 Float32 output"))

    return vectors

@block_spec("BandpassFilterBlock", "tests/blocks/signal/bandpassfilter_spec.lua")
def generate_bandpassfilter_spec():
    def process(num_taps, cutoffs, x):
        b = scipy.signal.firwin(num_taps, cutoffs, pass_zero=False, scale=False)
        return [scipy.signal.lfilter(b, 1, x).astype(type(x[0]))]

    vectors = []
    x = random_complex64(256)
    vectors.append(generate_test_vector(process, [129, [0.1, 0.3]], [x], "129 taps, {0.1, 0.3} cutoff, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [129, [0.4, 0.6]], [x], "129 taps, {0.4, 0.6} cutoff, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    x = random_float32(256)
    vectors.append(generate_test_vector(process, [129, [0.1, 0.3]], [x], "129 taps, {0.1, 0.3} cutoff, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [129, [0.4, 0.6]], [x], "129 taps, {0.4, 0.6} cutoff, 256 Float32 input, 256 Float32 output"))

    return vectors

@block_spec("BandstopFilterBlock", "tests/blocks/signal/bandstopfilter_spec.lua")
def generate_bandstopfilter_spec():
    def process(num_taps, cutoffs, x):
        b = scipy.signal.firwin(num_taps, cutoffs, pass_zero=True, scale=False)
        return [scipy.signal.lfilter(b, 1, x).astype(type(x[0]))]

    vectors = []
    x = random_complex64(256)
    vectors.append(generate_test_vector(process, [129, [0.1, 0.3]], [x], "129 taps, {0.1, 0.3} cutoff, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [129, [0.4, 0.6]], [x], "129 taps, {0.4, 0.6} cutoff, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    x = random_float32(256)
    vectors.append(generate_test_vector(process, [129, [0.1, 0.3]], [x], "129 taps, {0.1, 0.3} cutoff, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [129, [0.4, 0.6]], [x], "129 taps, {0.4, 0.6} cutoff, 256 Float32 input, 256 Float32 output"))

    return vectors

@block_spec("FMDeemphasisFilterBlock",  "tests/blocks/signal/fmdeemphasisfilter_spec.lua")
def generate_fmdeemphasisfilter_spec():
    def process(tau, x):
        b_taps = [1/(1 + 4*tau), 1/(1 + 4*tau)]
        a_taps = [1, (1 - 4*tau)/(1 + 4*tau)]
        return [scipy.signal.lfilter(b_taps, a_taps, x).astype(numpy.float32)]

    vectors = []
    x = random_float32(256)
    vectors.append(generate_test_vector(process, [75e-6], [x], "75e-6 tau, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [50e-6], [x], "50e-6 tau, 256 Float32 input, 256 Float32 output"))

    return vectors

@block_spec("RootRaisedCosineFilterBlock", "tests/blocks/signal/rootraisedcosinefilter_spec.lua")
def generate_rootraisedcosinefilter_spec():
    def process(num_taps, beta, symbol_rate, x):
        b = fir_root_raised_cosine(num_taps, 2.0, beta, 1/symbol_rate)
        return [scipy.signal.lfilter(b, 1, x).astype(type(x[0]))]

    vectors = []
    x = random_complex64(256)
    vectors.append(generate_test_vector(process, [101, 0.5, 1e-3], [x], "101 taps, 0.5 beta, 1e-3 symbol rate, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [101, 0.7, 1e-3], [x], "101 taps, 0.7 beta, 1e-3 symbol rate, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [101, 1.0, 5e-3], [x], "101 taps, 1.0 beta, 5e-3 symbol rate, 256 ComplexFloat32 input, 256 ComplexFloat32 output"))
    x = random_float32(256)
    vectors.append(generate_test_vector(process, [101, 0.5, 1e-3], [x], "101 taps, 0.5 beta, 1e-3 symbol rate, 256 Float32 input, 256 ComplexFloat32 output"))
    vectors.append(generate_test_vector(process, [101, 0.7, 1e-3], [x], "101 taps, 0.7 beta, 1e-3 symbol rate, 256 Float32 input, 256 Float32 output"))
    vectors.append(generate_test_vector(process, [101, 1.0, 5e-3], [x], "101 taps, 1.0 beta, 5e-3 symbol rate, 256 Float32 input, 256 Float32 output"))

    return vectors

@block_spec("RDSFrameBlock", "tests/blocks/protocol/rdsframe_spec.lua")
def generate_rdsframe_spec():
    class RDSFrame:
        def __init__(self, *blocks):
            self.blocks = blocks

        def serialize(self):
            return "{{{0x%04x, 0x%04x, 0x%04x, 0x%04x}}}" % self.blocks

    class RDSFrameVector(CustomVector):
        def __init__(self, *frames):
            self.frames = frames

        def serialize(self):
            t = [frame.serialize() for frame in self.frames]
            return "require('radio.blocks.protocol.rdsframe').RDSFrameType.vector_from_array({" + ", ".join(t) + "})"

    def process_maker(index):
        if index == 1:
            return lambda x: [RDSFrameVector(RDSFrame(0x3aab, 0x02c9, 0x0608, 0x6469))]
        elif index == 2:
            return lambda x: [RDSFrameVector(RDSFrame(0x3aab, 0x82c8, 0x4849, 0x2918))]
        elif index == 3:
            return lambda x: [RDSFrameVector(RDSFrame(0x3aab, 0x02ca, 0xe30a, 0x6f20))]
        elif index == 7:
            return lambda x: [RDSFrameVector(RDSFrame(0x3aab, 0x02c9, 0x0608, 0x6469), RDSFrame(0x3aab, 0x82c8, 0x4849, 0x2918), RDSFrame(0x3aab, 0x02ca, 0xe30a, 0x6f20))]

    vectors = []

    bits = numpy.array([0,0,1,1,1,0,1,0,1,0,1,0,1,0,1,1,0,1,1,1,0,1,1,0,0,0,0,0,0,0,0,0,1,0,1,1,0,0,1,0,0,1,1,0,1,1,0,0,0,0,1,1,0,0,0,0,0,1,1,0,0,0,0,0,1,0,0,0,0,0,1,0,1,0,0,0,1,1,0,1,1,0,0,1,0,0,0,1,1,0,1,0,0,1,1,1,1,1,0,0,0,1,1,0]).astype(numpy.bool_)
    x = numpy.hstack([random_bit(20), bits, random_bit(20)])
    vectors.append(generate_test_vector(process_maker(1), [], [x], "Valid frame 1"))

    bits = numpy.array([0,0,1,1,1,0,1,0,1,0,1,0,1,0,1,1,0,1,1,1,0,1,1,0,0,0,1,0,0,0,0,0,1,0,1,1,0,0,1,0,0,0,1,1,0,0,0,0,1,1,0,1,0,1,0,0,1,0,0,0,0,1,0,0,1,0,0,1,1,0,0,1,0,1,1,0,1,1,0,0,1,0,1,0,0,1,0,0,0,1,1,0,0,0,0,1,0,0,1,0,0,0,1,0]).astype(numpy.bool_)
    x = numpy.hstack([random_bit(20), bits, random_bit(20)])
    vectors.append(generate_test_vector(process_maker(2), [], [x], "Valid frame 2"))

    bits = numpy.array([0,0,1,1,1,0,1,0,1,0,1,0,1,0,1,1,0,1,1,1,0,1,1,0,0,0,0,0,0,0,0,0,1,0,1,1,0,0,1,0,1,0,0,0,0,0,0,0,1,0,0,0,1,1,1,0,0,0,1,1,0,0,0,0,1,0,1,0,0,1,0,1,0,0,0,0,1,0,0,1,1,0,1,1,1,1,0,0,1,0,0,0,0,0,1,1,0,1,1,1,0,1,1,0]).astype(numpy.bool_)
    x = numpy.hstack([random_bit(20), bits, random_bit(20)])
    vectors.append(generate_test_vector(process_maker(3), [], [x], "Valid frame 3"))

    bits = numpy.array([0,0,1,1,1,0,1,1,1,0,1,0,1,0,1,1,0,1,1,1,0,1,1,0,0,0,0,0,0,0,0,0,1,0,1,1,0,0,1,0,0,1,1,0,1,1,0,0,0,0,1,1,0,0,0,0,0,1,1,0,0,0,0,0,1,0,0,0,0,0,1,0,1,0,0,0,1,1,0,1,1,0,0,1,0,0,0,1,1,0,1,0,0,1,1,1,1,1,0,0,0,1,1,0]).astype(numpy.bool_)
    x = numpy.hstack([random_bit(20), bits, random_bit(20)])
    vectors.append(generate_test_vector(process_maker(1), [], [x], "Frame 1 with message bit error"))

    bits = numpy.array([0,0,1,1,1,0,1,0,1,0,1,0,1,0,1,1,0,1,1,0,0,1,1,0,0,0,1,0,0,0,0,0,1,0,1,1,0,0,1,0,0,0,1,1,0,0,0,0,1,1,0,1,0,1,0,0,1,0,0,0,0,1,0,0,1,0,0,1,1,0,0,1,0,1,1,0,1,1,0,0,1,0,1,0,0,1,0,0,0,1,1,0,0,0,0,1,0,0,1,0,0,0,1,0]).astype(numpy.bool_)
    x = numpy.hstack([random_bit(20), bits, random_bit(20)])
    vectors.append(generate_test_vector(process_maker(2), [], [x], "Frame 2 with crc bit error"))

    bits1 = numpy.array([0,0,1,1,1,0,1,0,1,0,1,0,1,0,1,1,0,1,1,1,0,1,1,0,0,0,0,0,0,0,0,0,1,0,1,1,0,0,1,0,0,1,1,0,1,1,0,0,0,0,1,1,0,0,0,0,0,1,1,0,0,0,0,0,1,0,0,0,0,0,1,0,1,0,0,0,1,1,0,1,1,0,0,1,0,0,0,1,1,0,1,0,0,1,1,1,1,1,0,0,0,1,1,0]).astype(numpy.bool_)
    bits2 = numpy.array([0,0,1,1,1,0,1,0,1,0,1,0,1,0,1,1,0,1,1,1,0,1,1,0,0,0,1,0,0,0,0,0,1,0,1,1,0,0,1,0,0,0,1,1,0,0,0,0,1,1,0,1,0,1,0,0,1,0,0,0,0,1,0,0,1,0,0,1,1,0,0,1,0,1,1,0,1,1,0,0,1,0,1,0,0,1,0,0,0,1,1,0,0,0,0,1,0,0,1,0,0,0,1,0]).astype(numpy.bool_)
    bits3 = numpy.array([0,0,1,1,1,0,1,0,1,0,1,0,1,0,1,1,0,1,1,1,0,1,1,0,0,0,0,0,0,0,0,0,1,0,1,1,0,0,1,0,1,0,0,0,0,0,0,0,1,0,0,0,1,1,1,0,0,0,1,1,0,0,0,0,1,0,1,0,0,1,0,1,0,0,0,0,1,0,0,1,1,0,1,1,1,1,0,0,1,0,0,0,0,0,1,1,0,1,1,1,0,1,1,0]).astype(numpy.bool_)
    x = numpy.hstack([bits1, bits2, bits3])
    vectors.append(generate_test_vector(process_maker(7), [], [x], "Three contiguous frames"))

    return vectors

@raw_spec("tests/blocks/sources/fileiqdescriptor_spec.lua")
def generate_fileiqdescriptor_spec():
    numpy_vectors = [
        # Format, numpy array, byteswap
        ( "u8", numpy.array(numpy.random.randint(0, 255, 256*2), dtype=numpy.uint8), False ),
        ( "s8", numpy.array(numpy.random.randint(-128, 127, 256*2), dtype=numpy.int8), False ),
        ( "u16le", numpy.array(numpy.random.randint(0, 65535, 256*2), dtype=numpy.uint16), False ),
        ( "u16be", numpy.array(numpy.random.randint(0, 65535, 256*2), dtype=numpy.uint16), True ),
        ( "s16le", numpy.array(numpy.random.randint(-32768, 32767, 256*2), dtype=numpy.int16), False ),
        ( "s16be", numpy.array(numpy.random.randint(-32768, 32767, 256*2), dtype=numpy.int16), True ),
        ( "u32le", numpy.array(numpy.random.randint(0, 4294967295, 256*2), dtype=numpy.uint32), False ),
        ( "u32be", numpy.array(numpy.random.randint(0, 4294967295, 256*2), dtype=numpy.uint32), True ),
        ( "s32le", numpy.array(numpy.random.randint(-2147483648, 2147483647, 256*2), dtype=numpy.int32), False ),
        ( "s32be", numpy.array(numpy.random.randint(-2147483648, 2147483647, 256*2), dtype=numpy.int32), True ),
        ( "f32le", numpy.array(numpy.around(numpy.random.rand(256*2), PRECISION), dtype=numpy.float32), False ),
        ( "f32be", numpy.array(numpy.around(numpy.random.rand(256*2), PRECISION), dtype=numpy.float32), True ),
        ( "f64le", numpy.array(numpy.around(numpy.random.rand(256*2), PRECISION), dtype=numpy.float64), False ),
        ( "f64be", numpy.array(numpy.around(numpy.random.rand(256*2), PRECISION), dtype=numpy.float64), True),
    ]

    def ascomplex64(x):
        if type(x[0]) == numpy.uint8:
            y = ((x - 127.5) / 127.5).astype(numpy.float32)
        elif type(x[0]) == numpy.int8:
            y = ((x - 0) / 127.5).astype(numpy.float32)
        elif type(x[0]) == numpy.uint16:
            y = ((x - 32767.5) / 32767.5).astype(numpy.float32)
        elif type(x[0]) == numpy.int16:
            y = ((x - 0) / 32767.5).astype(numpy.float32)
        elif type(x[0]) == numpy.uint32:
            y = ((x - 2147483647.5) / 2147483647.5).astype(numpy.float32)
        elif type(x[0]) == numpy.int32:
            y = ((x - 0) / 2147483647.5).astype(numpy.float32)
        elif type(x[0]) == numpy.float32:
            y = x
        elif type(x[0]) == numpy.float64:
            y = x.astype(numpy.float32)
        return numpy.around(numpy.array([numpy.complex64(complex(y[i], y[i+1])) for i in range(0, len(y), 2)]), PRECISION)

    vectors = []

    # Header
    vectors.append("local radio = require('radio')")
    vectors.append("")
    vectors.append("local jigs = require('tests.jigs')")
    vectors.append("local buffer = require('tests.buffer')")
    vectors.append("")

    # Vectors
    vectors.append("jigs.TestSourceBlock(radio.FileIQDescriptorSource, {")
    for (fmt, array, byteswap) in numpy_vectors:
        # Build byte array
        buf = array.tobytes() if not byteswap else array.byteswap().tobytes()
        buf = ''.join(["\\x%02x" % b for b in buf])

        # Serialize expected output
        expected_output = serialize(ascomplex64(array))

        vectors.append("\t{")
        vectors.append("\t\targs = {buffer.open(\"%s\"), \"%s\", 1}," % (buf, fmt))
        vectors.append("\t\toutputs = {%s}," % expected_output)
        vectors.append("\t},")
    vectors.append("}, {epsilon = %.1e})" % EPSILON)

    return vectors

@raw_spec("tests/blocks/sources/filedescriptor_spec.lua")
def generate_filedescriptor_spec():
    numpy_vectors = [
        # Format, numpy array, byteswap
        ( "u8", numpy.array(numpy.random.randint(0, 255, 256*2), dtype=numpy.uint8), False ),
        ( "s8", numpy.array(numpy.random.randint(-128, 127, 256*2), dtype=numpy.int8), False ),
        ( "u16le", numpy.array(numpy.random.randint(0, 65535, 256*2), dtype=numpy.uint16), False ),
        ( "u16be", numpy.array(numpy.random.randint(0, 65535, 256*2), dtype=numpy.uint16), True ),
        ( "s16le", numpy.array(numpy.random.randint(-32768, 32767, 256*2), dtype=numpy.int16), False ),
        ( "s16be", numpy.array(numpy.random.randint(-32768, 32767, 256*2), dtype=numpy.int16), True ),
        ( "u32le", numpy.array(numpy.random.randint(0, 4294967295, 256*2), dtype=numpy.uint32), False ),
        ( "u32be", numpy.array(numpy.random.randint(0, 4294967295, 256*2), dtype=numpy.uint32), True ),
        ( "s32le", numpy.array(numpy.random.randint(-2147483648, 2147483647, 256*2), dtype=numpy.int32), False ),
        ( "s32be", numpy.array(numpy.random.randint(-2147483648, 2147483647, 256*2), dtype=numpy.int32), True ),
        ( "f32le", numpy.array(numpy.around(numpy.random.rand(256*2), PRECISION), dtype=numpy.float32), False ),
        ( "f32be", numpy.array(numpy.around(numpy.random.rand(256*2), PRECISION), dtype=numpy.float32), True ),
        ( "f64le", numpy.array(numpy.around(numpy.random.rand(256*2), PRECISION), dtype=numpy.float64), False ),
        ( "f64be", numpy.array(numpy.around(numpy.random.rand(256*2), PRECISION), dtype=numpy.float64), True),
    ]

    def asfloat32(x):
        if type(x[0]) == numpy.uint8:
            y = ((x - 127.5) / 127.5).astype(numpy.float32)
        elif type(x[0]) == numpy.int8:
            y = ((x - 0) / 127.5).astype(numpy.float32)
        elif type(x[0]) == numpy.uint16:
            y = ((x - 32767.5) / 32767.5).astype(numpy.float32)
        elif type(x[0]) == numpy.int16:
            y = ((x - 0) / 32767.5).astype(numpy.float32)
        elif type(x[0]) == numpy.uint32:
            y = ((x - 2147483647.5) / 2147483647.5).astype(numpy.float32)
        elif type(x[0]) == numpy.int32:
            y = ((x - 0) / 2147483647.5).astype(numpy.float32)
        elif type(x[0]) == numpy.float32:
            y = x
        elif type(x[0]) == numpy.float64:
            y = x.astype(numpy.float32)
        return numpy.around(y, PRECISION)

    vectors = []

    # Header
    vectors.append("local radio = require('radio')")
    vectors.append("")
    vectors.append("local jigs = require('tests.jigs')")
    vectors.append("local buffer = require('tests.buffer')")
    vectors.append("")

    # Vectors
    vectors.append("jigs.TestSourceBlock(radio.FileDescriptorSource, {")
    for (fmt, array, byteswap) in numpy_vectors:
        # Build byte array
        buf = array.tobytes() if not byteswap else array.byteswap().tobytes()
        buf = ''.join(["\\x%02x" % b for b in buf])

        # Serialize expected output
        expected_output = serialize(asfloat32(array))

        vectors.append("\t{")
        vectors.append("\t\targs = {buffer.open(\"%s\"), \"%s\", 1}," % (buf, fmt))
        vectors.append("\t\toutputs = {%s}," % expected_output)
        vectors.append("\t},")
    vectors.append("}, {epsilon = %.1e})" % EPSILON)

    return vectors

################################################################################

if __name__ == "__main__":
    for s in AllSpecs:
        s()
