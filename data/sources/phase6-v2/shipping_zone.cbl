       IDENTIFICATION DIVISION.
       PROGRAM-ID. SHIPZONE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-WEIGHT  PIC 9(5) VALUE 0.
       01 WS-ZONE    PIC 9 VALUE 1.
       01 WS-COST    PIC 9(5) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM BASE-COST.
           PERFORM ZONE-SURCHARGE.
           DISPLAY WS-COST.
           STOP RUN.
       BASE-COST.
           IF WS-WEIGHT > 50
               MOVE 1500 TO WS-COST
           ELSE
               MOVE 700 TO WS-COST
           END-IF.
       ZONE-SURCHARGE.
           IF WS-ZONE >= 3
               ADD 400 TO WS-COST
           END-IF.
