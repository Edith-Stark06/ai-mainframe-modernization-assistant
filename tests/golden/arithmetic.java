public class ArithmeticTest {

    private int numA;
    private int numB;

    public static void main(String[] args) {
        new ArithmeticTest().run();
    }

    public void run() {

        numB += numA;
        numB -= 2;
        numB *= numA;
        numB /= 3;

    }

}
