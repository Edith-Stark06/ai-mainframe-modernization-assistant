* DATA DIVISION SECTION AND CLAUSE REGRESSION FIXTURE (task #105)
* Exercises the constructs whose handling depended on token-type gates:
*   - an unsupported section (FILE SECTION) that must be skipped safely
*   - a SUPPORTED section (WORKING-STORAGE) *after* the unsupported one,
*     which was previously lost entirely
*   - a packed-decimal USAGE clause (COMP-3)
*   - a REDEFINES clause
*   - a PROCEDURE DIVISION that must still be reached, with its
*     statements intact
* Paragraph name is deliberately alphabetic: the lexer cannot yet
* tokenise numeric-prefixed names such as 0000-MAIN (see #105 report).
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST-PROGRAM.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       FILE SECTION.
       FD INPUT-FILE.
       01 INPUT-REC PIC X(100).
       WORKING-STORAGE SECTION.
       01 WS-COUNT PIC 9(4).
       01 WS-AMOUNT PIC S9(7)V99 COMP-3.
       01 WS-ALT PIC X(5) REDEFINES WS-COUNT.
       PROCEDURE DIVISION.
       MAIN.
           DISPLAY WS-COUNT.
           STOP RUN.
