/*
 * test_utils.h — minimal host-side unit test harness. No dependencies.
 */

#ifndef TEST_UTILS_H
#define TEST_UTILS_H

#include <stdio.h>
#include <math.h>

static int _tests_run    = 0;
static int _tests_failed = 0;

#define TEST_ASSERT(cond)                                                \
    do { if (!(cond)) {                                                  \
        fprintf(stderr, "  FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
        _tests_failed++; return;                                         \
    } } while (0)

#define TEST_ASSERT_FLOAT_NEAR(a, b, tol)                                \
    do {                                                                 \
        float _a = (float)(a), _b = (float)(b), _t = (float)(tol);     \
        if (fabsf(_a - _b) > _t) {                                      \
            fprintf(stderr, "  FAIL %s:%d: |%s - %s| = %g > %g\n",     \
                    __FILE__, __LINE__, #a, #b,                         \
                    (double)fabsf(_a - _b), (double)_t);                \
            _tests_failed++; return;                                     \
        }                                                                \
    } while (0)

#define TEST_ASSERT_INT_EQ(a, b)                                         \
    do {                                                                 \
        long long _a = (long long)(a), _b = (long long)(b);            \
        if (_a != _b) {                                                  \
            fprintf(stderr, "  FAIL %s:%d: %s=%lld, %s=%lld\n",        \
                    __FILE__, __LINE__, #a, _a, #b, _b);                \
            _tests_failed++; return;                                     \
        }                                                                \
    } while (0)

#define RUN_TEST(func)                                                   \
    do {                                                                 \
        int _before = _tests_failed;                                    \
        _tests_run++;                                                    \
        func();                                                          \
        printf("%s: %s\n", (_tests_failed == _before) ? "PASS" : "FAIL", #func); \
    } while (0)

#define TEST_REPORT() \
    (printf("\n%d/%d passed.\n", _tests_run - _tests_failed, _tests_run), \
     (_tests_failed > 0) ? 1 : 0)

#endif /* TEST_UTILS_H */
