#  Copyright (c) 2016-2017 Rocky Bernstein
"""
spark grammar differences over Python 3.5 for Python 3.6.
"""
from __future__ import print_function

from uncompyle6.parser import PythonParserSingle, nop_func
from spark_parser import DEFAULT_DEBUG as PARSER_DEFAULT_DEBUG
from uncompyle6.parsers.parse35 import Python35Parser

class Python36Parser(Python35Parser):

    def __init__(self, debug_parser=PARSER_DEFAULT_DEBUG):
        super(Python36Parser, self).__init__(debug_parser)
        self.customized = {}


    def p_36misc(self, args):
        """
        # 3.6 redoes how return_closure works
        return_closure   ::= LOAD_CLOSURE DUP_TOP STORE_NAME RETURN_VALUE RETURN_LAST

        stmt               ::= conditional_lambda
        conditional_lambda ::= expr jmp_false expr return_if_lambda
                               return_stmt_lambda LAMBDA_MARKER
        return_stmt_lambda ::= ret_expr RETURN_VALUE_LAMBDA
        return_if_lambda   ::= RETURN_END_IF_LAMBDA


        for_block       ::= l_stmts_opt come_from_loops JUMP_BACK
        come_from_loops ::= COME_FROM_LOOP*


        # This might be valid in < 3.6
        and  ::= expr jmp_false expr

        # Adds a COME_FROM_ASYNC_WITH over 3.5
        # FIXME: remove corresponding rule for 3.5?

        except_suite ::= c_stmts_opt COME_FROM POP_EXCEPT jump_except COME_FROM

        # In 3.6+, A sequence of statements ending in a RETURN can cause
        # JUMP_FORWARD END_FINALLY to be omitted from try middle

        except_return    ::= POP_TOP POP_TOP POP_TOP returns
        except_handler   ::= JUMP_FORWARD COME_FROM_EXCEPT except_return

        # Try middle following a returns
        except_handler36 ::= COME_FROM_EXCEPT except_stmts END_FINALLY

        stmt             ::= try_except36
        try_except36     ::= SETUP_EXCEPT returns except_handler36 opt_come_from_except
        """

    def customize_grammar_rules(self, tokens, customize):
        super(Python36Parser, self).customize_grammar_rules(tokens, customize)
        for i, token in enumerate(tokens):
            opname = token.kind

            if opname == 'FORMAT_VALUE':
                rules_str = """
                    expr ::= fstring_single
                    fstring_single ::= expr FORMAT_VALUE
                """
                self.add_unique_doc_rules(rules_str, customize)
            elif opname == 'BEFORE_ASYNC_WITH':
                rules_str = """
                  stmt ::= async_with_stmt
                  async_with_as_stmt ::= expr
                               BEFORE_ASYNC_WITH GET_AWAITABLE LOAD_CONST YIELD_FROM
                               SETUP_ASYNC_WITH store
                               suite_stmts_opt
                               POP_BLOCK LOAD_CONST
                               COME_FROM_ASYNC_WITH
                               WITH_CLEANUP_START
                               GET_AWAITABLE LOAD_CONST YIELD_FROM
                               WITH_CLEANUP_FINISH END_FINALLY
                 stmt ::= async_with_as_stmt
                 async_with_stmt ::= expr
                               BEFORE_ASYNC_WITH GET_AWAITABLE LOAD_CONST YIELD_FROM
                               SETUP_ASYNC_WITH POP_TOP suite_stmts_opt
                               POP_BLOCK LOAD_CONST
                               COME_FROM_ASYNC_WITH
                               WITH_CLEANUP_START
                               GET_AWAITABLE LOAD_CONST YIELD_FROM
                               WITH_CLEANUP_FINISH END_FINALLY
                """
                self.addRule(rules_str, nop_func)

            elif opname == 'BUILD_STRING':
                v = token.attr
                joined_str_n = "formatted_value_%s" % v
                rules_str = """
                    expr            ::= fstring_expr
                    fstring_expr    ::= expr FORMAT_VALUE
                    str             ::= LOAD_CONST
                    formatted_value ::= fstring_expr
                    formatted_value ::= str

                    expr                 ::= fstring_multi
                    fstring_multi        ::= joined_str BUILD_STRING
                    joined_str           ::= formatted_value+
                    fstring_multi        ::= %s BUILD_STRING
                    %s                   ::= %sBUILD_STRING
                """ % (joined_str_n, joined_str_n, "formatted_value " * v)
                self.add_unique_doc_rules(rules_str, customize)
            elif opname.startswith('BUILD_MAP_UNPACK_WITH_CALL'):
                v = token.attr
                rule = ('build_map_unpack_with_call ::= ' + 'expr1024 ' * int(v//1024) +
                        'expr32 ' * int((v//32) % 32) +
                        'expr ' * (v % 32) + opname)
                self.addRule(rule, nop_func)
            elif opname.startswith('BUILD_TUPLE_UNPACK_WITH_CALL'):
                v = token.attr
                rule = ('build_tuple_unpack_with_call ::= ' + 'expr1024 ' * int(v//1024) +
                        'expr32 ' * int((v//32) % 32) +
                        'expr ' * (v % 32) + opname)
                self.addRule(rule, nop_func)
            elif opname == 'SETUP_WITH':
                rules_str = """
                withstmt   ::= expr SETUP_WITH POP_TOP suite_stmts_opt POP_BLOCK LOAD_CONST
                               WITH_CLEANUP_START WITH_CLEANUP_FINISH END_FINALLY
                withstmt   ::= expr SETUP_WITH POP_TOP suite_stmts_opt COME_FROM_WITH
                               WITH_CLEANUP_START WITH_CLEANUP_FINISH END_FINALLY

                # Removes POP_BLOCK LOAD_CONST from 3.6-
                withasstmt ::= expr SETUP_WITH store suite_stmts_opt COME_FROM_WITH
                               WITH_CLEANUP_START WITH_CLEANUP_FINISH END_FINALLY
                """
                self.addRule(rules_str, nop_func)

    def custom_classfunc_rule(self, opname, token, customize,
                              possible_class_decorator,
                              seen_GET_AWAITABLE_YIELD_FROM, next_token):
        if opname.startswith('CALL_FUNCTION_KW'):
            self.addRule("expr ::= call_kw", nop_func)
            values = 'expr ' * token.attr
            rule = 'call_kw ::= expr kwargs_36 {token.kind}'.format(**locals())
            self.addRule(rule, nop_func)
            rule = 'kwargs_36 ::= {values} LOAD_CONST'.format(**locals())
            self.add_unique_rule(rule, token.kind, token.attr, customize)
        elif opname == 'CALL_FUNCTION_EX_KW':
            self.addRule("""expr        ::= call_ex_kw
                            expr        ::= call_ex_kw2
                            expr        ::= call_ex_kw3
                            call_ex_kw  ::= expr expr build_map_unpack_with_call
                                            CALL_FUNCTION_EX_KW
                            call_ex_kw2 ::= expr
                                            build_tuple_unpack_with_call
                                            build_map_unpack_with_call
                                            CALL_FUNCTION_EX_KW
                            call_ex_kw3 ::= expr
                                            expr
                                            expr
                                            CALL_FUNCTION_EX_KW
                         """,
                         nop_func)
        elif opname == 'CALL_FUNCTION_EX':
            self.addRule("""
                         expr        ::= call_ex
                         starred     ::= expr
                         call_ex     ::= expr starred CALL_FUNCTION_EX
                         """, nop_func)
            pass
        else:
            super(Python36Parser, self).custom_classfunc_rule(opname, token,
                                                              customize,
                                                              possible_class_decorator,
                                                              seen_GET_AWAITABLE_YIELD_FROM,
                                                              next_token)

class Python36ParserSingle(Python36Parser, PythonParserSingle):
    pass

if __name__ == '__main__':
    # Check grammar
    p = Python36Parser()
    p.check_grammar()
    from uncompyle6 import PYTHON_VERSION, IS_PYPY
    if PYTHON_VERSION == 3.6:
        lhs, rhs, tokens, right_recursive = p.check_sets()
        from uncompyle6.scanner import get_scanner
        s = get_scanner(PYTHON_VERSION, IS_PYPY)
        opcode_set = set(s.opc.opname).union(set(
            """JUMP_BACK CONTINUE RETURN_END_IF COME_FROM
               LOAD_GENEXPR LOAD_ASSERT LOAD_SETCOMP LOAD_DICTCOMP LOAD_CLASSNAME
               LAMBDA_MARKER RETURN_LAST
            """.split()))
        remain_tokens = set(tokens) - opcode_set
        import re
        remain_tokens = set([re.sub('_\d+$', '', t) for t in remain_tokens])
        remain_tokens = set([re.sub('_CONT$', '', t) for t in remain_tokens])
        remain_tokens = set(remain_tokens) - opcode_set
        print(remain_tokens)
        # print(sorted(p.rule2name.items()))
