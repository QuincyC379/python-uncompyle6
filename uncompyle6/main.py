from __future__ import print_function
import datetime, os, subprocess, sys, tempfile

from uncompyle6 import verify, IS_PYPY, PYTHON_VERSION
from xdis.code import iscode
from uncompyle6.disas import check_object_path
from uncompyle6.semantics import pysource
from uncompyle6.parser import ParserError
from uncompyle6.version import VERSION
# from uncompyle6.linenumbers import line_number_mapping

from uncompyle6.semantics.pysource import deparse_code
from uncompyle6.semantics.fragments import deparse_code as deparse_code_fragments
from uncompyle6.semantics.linemap import deparse_code_with_map

from xdis.load import load_module

def _get_outstream(outfile):
    dir = os.path.dirname(outfile)
    failed_file = outfile + '_failed'
    if os.path.exists(failed_file):
        os.remove(failed_file)
    try:
        os.makedirs(dir)
    except OSError:
        pass
    return open(outfile, 'w')

def decompile(
        bytecode_version, co, out=None, showasm=None, showast=False,
        timestamp=None, showgrammar=False, code_objects={},
        source_size=None, is_pypy=False, magic_int=None,
        mapstream=None, do_fragments=False):
    """
    ingests and deparses a given code block 'co'

    Caller is responsible for closing `out` and `mapstream`
    """
    # store final output stream for case of error
    real_out = out or sys.stdout

    def write(s):
        s += '\n'
        real_out.write(s)

    assert iscode(co)

    co_pypy_str = 'PyPy ' if is_pypy else ''
    run_pypy_str = 'PyPy ' if IS_PYPY else ''
    sys_version_lines = sys.version.split('\n')
    write('# uncompyle6 version %s\n'
          '# %sPython bytecode %s%s\n# Decompiled from: %sPython %s' %
          (VERSION, co_pypy_str, bytecode_version,
               " (%s)" % str(magic_int) if magic_int else "",
          run_pypy_str, '\n# '.join(sys_version_lines)))
    if co.co_filename:
        write('# Embedded file name: %s' % co.co_filename,)
    if timestamp:
        write('# Compiled at: %s' % datetime.datetime.fromtimestamp(timestamp))
    if source_size:
        write('# Size of source mod 2**32: %d bytes' % source_size)

    try:
        if mapstream:
            if isinstance(mapstream, str):
                mapstream = _get_outstream(mapstream)

            deparsed = deparse_code_with_map(bytecode_version, co, out, showasm, showast,
                                             showgrammar,
                                             code_objects = code_objects,
                                             is_pypy = is_pypy,
                                             )
            header_count = 3+len(sys_version_lines)
            linemap = [(line_no, deparsed.source_linemap[line_no]+header_count)
                        for line_no in
                        sorted(deparsed.source_linemap.keys())]
            mapstream.write("\n\n# %s\n" % linemap)
        else:
            if do_fragments:
                deparse_fn = deparse_code_fragments
            else:
                deparse_fn = deparse_code
            deparsed = deparse_fn(bytecode_version, co, out, showasm, showast,
                                  showgrammar, code_objects=code_objects,
                                      is_pypy=is_pypy)
            pass
        return deparsed
    except pysource.SourceWalkerError as e:
        # deparsing failed
        raise pysource.SourceWalkerError(str(e))

def decompile_file(filename, outstream=None, showasm=None, showast=False,
                   showgrammar=False, mapstream=None, do_fragments=False):
    """
    decompile Python byte-code file (.pyc). Return objects to
    all of the deparsed objects found in `filename`.
    """

    filename = check_object_path(filename)
    code_objects = {}
    (version, timestamp, magic_int, co, is_pypy,
        source_size) = load_module(filename, code_objects)

    if isinstance(co, list):
        deparsed = []
        for con in co:
            deparsed.append(
                decompile(version, con, outstream, showasm, showast,
                          timestamp, showgrammar, code_objects=code_objects,
                          is_pypy=is_pypy, magic_int=magic_int),
                          mapstream=mapstream)
    else:
        deparsed = [decompile(version, co, outstream, showasm, showast,
                              timestamp, showgrammar,
                              code_objects=code_objects, source_size=source_size,
                              is_pypy=is_pypy, magic_int=magic_int,
                              mapstream=mapstream, do_fragments=do_fragments)]
    co = None
    return deparsed


# FIXME: combine into an options parameter
def main(in_base, out_base, files, codes, outfile=None,
         showasm=None, showast=False, do_verify=False,
         showgrammar=False, raise_on_error=False,
         do_linemaps=False, do_fragments=False):
    """
    in_base	base directory for input files
    out_base	base directory for output files (ignored when
    files	list of filenames to be uncompyled (relative to src_base)
    outfile	write output to this filename (overwrites out_base)

    For redirecting output to
    - <filename>		outfile=<filename> (out_base is ignored)
    - files below out_base	out_base=...
    - stdout			out_base=None, outfile=None
    """
    tot_files = okay_files = failed_files = verify_failed_files = 0
    current_outfile = outfile
    linemap_stream = None

    for filename in files:
        infile = os.path.join(in_base, filename)
        if not os.path.exists(infile):
            sys.stderr.write("File '%s' doesn't exist. Skipped\n"
                             % infile)
            continue

        if do_linemaps:
            linemap_stream = infile + '.pymap'
            pass

        # print (infile, file=sys.stderr)

        if outfile: # outfile was given as parameter
            outstream = _get_outstream(outfile)
        elif out_base is None:
            outstream = sys.stdout
            if do_linemaps:
                linemap_stream = sys.stdout
            if do_verify:
                prefix = os.path.basename(filename) + '-'
                if prefix.endswith('.py'):
                    prefix = prefix[:-len('.py')]

                # Unbuffer output if possible
                buffering = -1 if sys.stdout.isatty() else 0
                if PYTHON_VERSION >= 3.5:
                    t = tempfile.NamedTemporaryFile(mode='w+b',
                                                    buffering=buffering,
                                                    suffix='.py',
                                                    prefix=prefix)
                else:
                    t = tempfile.NamedTemporaryFile(mode='w+b',
                                                    suffix='.py',
                                                    prefix=prefix)
                current_outfile = t.name
                sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering)
                tee = subprocess.Popen(["tee", current_outfile],
                                       stdin=subprocess.PIPE)
                os.dup2(tee.stdin.fileno(), sys.stdout.fileno())
                os.dup2(tee.stdin.fileno(), sys.stderr.fileno())
        else:
            if filename.endswith('.pyc'):
                current_outfile = os.path.join(out_base, filename[0:-1])
            else:
                current_outfile = os.path.join(out_base, filename) + '_dis'
                pass
            pass

            outstream = _get_outstream(current_outfile)

        # print(current_outfile, file=sys.stderr)

        # Try to uncompile the input file
        try:
            deparsed = decompile_file(infile, outstream, showasm, showast, showgrammar,
                                      linemap_stream, do_fragments)
            if do_fragments:
                for d in deparsed:
                    last_mod = None
                    offsets = d.offsets
                    for e in sorted([k for k in offsets.keys() if isinstance(k[1], int)]):
                        if e[0] != last_mod:
                            line = '=' * len(e[0])
                            outstream.write("%s\n%s\n%s\n" % (line, e[0], line))
                        last_mod = e[0]
                        info = offsets[e]
                        extractInfo = d.extract_node_info(info)
                        outstream.write("%s" % info.node.format().strip() + "\n")
                        outstream.write(extractInfo.selectedLine + "\n")
                        outstream.write(extractInfo.markerLine + "\n\n")
                    pass
                pass
            tot_files += 1
        except (ValueError, SyntaxError, ParserError, pysource.SourceWalkerError) as e:
            sys.stdout.write("\n")
            sys.stderr.write("\n# file %s\n# %s\n" % (infile, e))
            failed_files += 1
        except KeyboardInterrupt:
            if outfile:
                outstream.close()
                os.remove(outfile)
            sys.stdout.write("\n")
            sys.stderr.write("\nLast file: %s   " % (infile))
            raise
        # except:
        #     failed_files += 1
        #     if current_outfile:
        #         outstream.close()
        #         os.rename(current_outfile, current_outfile + '_failed')
        #     else:
        #         sys.stderr.write("\n# %s" % sys.exc_info()[1])
        #         sys.stderr.write("\n# Can't uncompile %s\n" % infile)
        else: # uncompile successful
            if current_outfile:
                outstream.close()

                if do_verify:
                    try:
                        msg = verify.compare_code_with_srcfile(infile,
                                                               current_outfile,
                                                               do_verify)
                        if not current_outfile:
                            if not msg:
                                print('\n# okay decompiling %s' % infile)
                                okay_files += 1
                            else:
                                verify_failed_files += 1
                                print('\n# %s\n\t%s', infile, msg)
                                pass
                        else:
                            okay_files += 1
                            pass
                    except verify.VerifyCmpError as e:
                        print(e)
                        verify_failed_files += 1
                        os.rename(current_outfile, current_outfile + '_unverified')
                        sys.stderr.write("### Error Verifying %s\n" % filename)
                        sys.stderr.write(str(e) + "\n")
                        if not outfile:
                            if raise_on_error:
                                raise
                            pass
                        pass
                    pass
                else:
                    okay_files += 1
                pass
            elif do_verify:
                sys.stderr.write("\n### uncompile successful, but no file to compare against\n")
                pass
            else:
                okay_files += 1
                if not current_outfile:
                    mess = '\n# okay decompiling'
                    # mem_usage = __memUsage()
                    print(mess, infile)
        if current_outfile:
            sys.stdout.write("%s\r" %
                             status_msg(do_verify, tot_files, okay_files, failed_files,
                                        verify_failed_files, do_verify))
            sys.stdout.flush()
    if current_outfile:
        sys.stdout.write("\n")
        sys.stdout.flush()
    return (tot_files, okay_files, failed_files, verify_failed_files)


# ---- main ----

if sys.platform.startswith('linux') and os.uname()[2][:2] in ['2.', '3.', '4.']:
    def __memUsage():
        mi = open('/proc/self/stat', 'r')
        mu = mi.readline().split()[22]
        mi.close()
        return int(mu) / 1000000
else:
    def __memUsage():
        return ''

def status_msg(do_verify, tot_files, okay_files, failed_files,
               verify_failed_files, weak_verify):
    if weak_verify == 'weak':
        verification_type = 'weak '
    elif weak_verify == 'verify-run':
        verification_type = 'run '
    else:
        verification_type = ''
    if tot_files == 1:
        if failed_files:
            return "\n# decompile failed"
        elif verify_failed_files:
            return "\n# decompile %sverification failed" % verification_type
        else:
            return "\n# Successfully decompiled file"
            pass
        pass
    mess = "decompiled %i files: %i okay, %i failed" % (tot_files, okay_files, failed_files)
    if do_verify:
        mess += (", %i %sverification failed" % (verify_failed_files, verification_type))
    return mess
