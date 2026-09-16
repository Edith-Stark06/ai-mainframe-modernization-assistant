       IDENTIFICATION DIVISION.
       PROGRAM-ID. STATUSMACH.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-STATUS   PIC X VALUE 'P'.
       01 WS-RESULT   PIC X(10) VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM ADVANCE-STATUS.
           PERFORM REPORT-STATUS.
           STOP RUN.
       ADVANCE-STATUS.
           IF WS-STATUS = 'P'
               MOVE 'A' TO WS-STATUS
           END-IF.
           IF WS-STATUS = 'A'
               MOVE 'C' TO WS-STATUS
           END-IF.
       REPORT-STATUS.
           IF WS-STATUS = 'C'
               MOVE 'CLOSED' TO WS-RESULT
           END-IF.
