* ENVIRONMENT DIVISION REGRESSION FIXTURE
* Mirrors the ENVIRONMENT DIVISION constructs actually present in the
* real 500-line complex_acctbatch.cbl program: a CONFIGURATION SECTION
* with SOURCE-COMPUTER / OBJECT-COMPUTER paragraphs, and an
* INPUT-OUTPUT SECTION with a FILE-CONTROL paragraph containing
* SELECT ... ASSIGN TO ... ORGANIZATION IS ... FILE STATUS IS ...
* clauses.
*
* Uses WORKING-STORAGE SECTION rather than FILE SECTION in the DATA
* DIVISION on purpose. FILE SECTION is a separate, pre-existing DATA
* DIVISION limitation, so keeping it out of this fixture isolates the
* ENVIRONMENT DIVISION behaviour actually under test here.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ENVTEST.
       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-Z.
       OBJECT-COMPUTER. IBM-Z.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCOUNT-FILE ASSIGN TO ACCTIN
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-ACCT-STATUS.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-ACCT-STATUS PIC X(02).
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY "OK".
           STOP RUN.
